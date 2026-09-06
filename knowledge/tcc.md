# WMD SDK TCC 流程分析（financialTrans 接口）

## 一、TCC 整体架构

该 SDK 实现的是**两阶段 TCC 分布式事务**（Try → Confirm/Cancel），由以下核心组件协作：

| 组件                                                         | 职责                                       |
| ------------------------------------------------------------ | ------------------------------------------ |
| `TccControlManager`                                          | 登记 TCC 事务（生成 TCC_ID、插入控制记录） |
| `TccSeqManager` / `TccSeqReloader`                           | 生成 20 位 TCC_ID（号段方式）              |
| `TransControlInfoManager`                                    | ThreadLocal 线程缓存事务上下文             |
| `TccControlAdapter`                                          | Spring 事务监听器，驱动二阶段触发          |
| `TccTransClient`                                             | Try 阶段发送报文到中台，记录 TCC 影像      |
| `TccComfirmer` / `TccCanceler`                               | 二阶段 Confirm / Cancel 发送器             |
| `TccCompleterExecutor`                                       | 二阶段失败后的记录、重试调度               |
| `WmdTccControlDao` / `WmdTccSeqCountDao` / `ErrortccImageDao` | 表操作 DAO                                 |

## 二、financialTrans 完整 TCC 流程

### 阶段 0：事务初始化（调用 financialTrans 之前）
`TransControlInfoManager.initTransControlInfo(wmdName, dbDivNam)` 在进入业务方法前被调用，它：
1. 校验当前存在 Spring 事务（无事务报错 `WMDSB1Z`）
2. 注册 `TccControlAdapter` 事务监听器
3. 创建 `TransControlInfo` 放入 ThreadLocal

### 阶段 1：Try 阶段（financialTrans 方法内）

**Step 1.1 — 登记 TCC（`TccControlManager.registTccControl`）**
```
registTccControl(entrySet, WMD1)
```
1. `checkWmdDbDiv`：校验套号属于同一中台应用、同一分库
2. `checkTcc`：校验 TCC 事务监听器已注册、事务未完成
3. **若同线程已有 TCC**（`hasTccControl`）：只 `addTccSequence()` 递增序号，**不重复登记**（同一 TCC 事务内多套交易共享一个 TCC_ID）
4. **否则首次登记**：
   - `tccSeqManager.getTccSequence()` 生成 20 位 TCC_ID（3 位产品码 + 分库实例 + 36 进制日期 + 11 位 36 进制序号）
   - `wmdTccControlDao.insertTccControl(...)` **插入 WMD_TCC_CONTROL_T，状态 = 'P'（REGISTER）**，独立事务（REQUIRES_NEW）
   - `lockTccControl(tccId)` 锁读该记录（`FOR UPDATE WAIT 3`），锁不到则报错 `WMDSB1Y`
   - `setTccId` 将 TCC_ID 和注册时间放入线程缓存

**Step 1.2 — 组装并发送 Try 报文（`FinancialTransManager.execTry`）**
1. 输入校验：交易列表非空、交易请求流水号不重复
2. 组装报文，包含：
   - `FinancialTransTry_X1`：TCC_ID、TCC 序号、注册时间、应用信息等
   - `FinancialTransTry_X2[]`：每笔金融交易的明细（卡号、账户、金额、币种等）
   - `FinancialTransTry_X3`：现金管理信息（CashReport）
   - `$ADRMSG$`：地址信息包
   - `AntiDuplicateX1[]`：防重流水
3. `tccTransClient.execute(request, entrySet)`：
   - `bypassKafkaManager.sendTccTryMsg(request)`：发送 Try 报文到 **Kafka**
   - `saveTccImageFromRequest`：将请求中实现 `TccImageGenerator` 的 DTO 记录到 `TransControlInfo.tccImageGeneratorMap`（记录本次 Try 涉及的所有**户口和银行账户影像**，供失败补偿用）
   - `super.doExecute`：通过 TCP 发送到中台 **WMD1**，中台执行 Try 业务（**冻结/预占资金、写交易流水**等，业务表由中台侧操作）
   - **若 Try 异常**：`setTryFailed()` 标记 tryFailed=true，二阶段将走 Cancel

### 阶段 2：二阶段触发（Spring 事务提交/回滚时，由 TccControlAdapter 驱动）

`TccControlAdapter` 是 `TransactionSynchronizationAdapter`，在 Spring 事务生命周期回调：

**beforeCommit（事务提交前）**
- 若 `tryFailed == true`：**禁止提交**，抛错 `WMDSB62`，强制回滚
- 否则：`updateTccControlStatus(tccId, CONFIRM)` **更新 WMD_TCC_CONTROL_T 状态 = 'C'（CONFIRM）**，与业务事务同事务

**afterCompletion（事务结束后）**
- `status == STATUS_COMMITTED`（提交成功）→ 设置 `tccCompleter = TccComfirmer`
- `status == STATUS_ROLLED_BACK`（回滚成功）→ 设置 `tccCompleter = TccCanceler`，并**新开事务** `updateTccControlStatusNewTransactional(tccId, CANCEL)` **更新 WMD_TCC_CONTROL_T 状态 = 'R'（CANCEL）**
- `status == STATUS_UNKNOWN` → 记录未知状态到 Kafka，不执行二阶段

**afterReturningDoCleanup（TccCompleterExecutor，事务方法返回后）**
- 若事务已完成且有 TCC_ID，调用 `tccCompleter.complete(transControlInfo)` 执行真正的二阶段：

**Confirm 路径（提交成功）— `TccComfirmer.complete`**
1. 组装 `Wmd1TccConfirm_X1`（TCC_ID + 注册时间）
2. `sendTccPgmMsg` 发送 Confirm 报文到 **Kafka**
3. TCP 发送到中台 WMD1，中台执行 Confirm（**正式入账、解除冻结、更新交易状态**）
4. 响应码非 `SUC0000` 则抛错

**Cancel 路径（回滚）— `TccCanceler.complete`**
1. 组装 `Wmd1TccCancel_X1`（TCC_ID + 注册时间）+ `Wmd1TccCancel_X2[]`（本次事务所有套号列表）
2. `sendTccPgmMsg` 发送 Cancel 报文到 **Kafka**
3. TCP 发送到中台 WMD1，中台执行 Cancel（**解冻资金、撤销流水、恢复余额**）
4. 响应码非 `SUC0000` 则抛错

**二阶段失败处理（TccCompleterExecutor.recordAndRecomplete）**
若 Confirm/Cancel 发送失败：
1. `errortccImageDao.batchInsert` **插入 WMD_ERRORTCC_IMAGE_T**（记录 TCC_ID、套号、涉及的户口卡号影像、银行账户影像），独立事务
2. `keyErrorManager.sendConfirmOrCancel` 发 Kafka 告警
3. 延迟 `delay` 秒（默认 2s）后，由 `recompleteExecutor`（ScheduledThreadPoolExecutor，3 线程）**自动重试二阶段**

## 三、各阶段改动的表

### SDK 侧直接操作的表（本 jar 内 DAO 可见）

| 表名                     | 操作               | 阶段                   | 说明                                                       |
| ------------------------ | ------------------ | ---------------------- | ---------------------------------------------------------- |
| **WMD_TCC_CONTROL_T**    | INSERT（状态='P'） | Try 登记               | TCC 控制主表，记录 TCC_ID、注册时间、状态、链路 ID         |
| **WMD_TCC_CONTROL_T**    | UPDATE（状态='C'） | beforeCommit           | 提交前更新为 CONFIRM                                       |
| **WMD_TCC_CONTROL_T**    | UPDATE（状态='R'） | afterCompletion 回滚时 | 新事务更新为 CANCEL                                        |
| **WMD_TCC_CONTROL_T**    | DELETE             | 定时清理               | `clearTccControl` 按注册时间清理过期记录                   |
| **WMD_TCCSEQ_COUNT_T**   | INSERT/UPDATE      | Try 登记（首次）       | TCC_ID 号段计数器表（产品码+分库实例维度），记录号段、日期 |
| **WMD_ERRORTCC_IMAGE_T** | INSERT             | 二阶段失败             | 错误 TCC 影像表，记录失败事务涉及的户口/银行账户，供补偿   |

### 中台（WMD1）侧操作的表（SDK 通过报文驱动，业务表由中台处理）

| 阶段        | 中台操作的表（典型）                                         | 说明                                              |
| ----------- | ------------------------------------------------------------ | ------------------------------------------------- |
| **Try**     | 交易流水表（冻结/预占）、账户余额冻结字段、防重流水表        | 冻结资金、记录交易流水（状态=Try/冻结）、登记防重 |
| **Confirm** | 交易流水表（状态更新）、账户余额（正式扣减/入账）、现金管理报表 | 正式入账、解除冻结、更新流水状态为成功            |
| **Cancel**  | 交易流水表（撤销）、账户余额（解冻恢复）                     | 解冻资金、撤销流水、恢复余额                      |

> 注：SDK 本身不直接操作业务表，业务表的增删改由中台（WMD1）在接收 TRY/CONFIRM/CANCEL 报文后完成。SDK 侧通过 `TccImageGenerator` 收集涉及户口/银行账户的"影像"，仅用于二阶段失败后写入 `WMD_ERRORTCC_IMAGE_T` 供人工/自动补偿。

## 四、关键设计要点

1. **TCC_ID 生成**：20 位，号段式（每次从 `WMD_TCCSEQ_COUNT_T` 取 1000 个号段），避免频繁访问数据库
2. **同事务多套交易**：同一线程内多个 `financialTrans` 调用共享一个 TCC_ID，通过 `tccSequence` 递增区分
3. **Try 失败保护**：`tryFailed` 标记确保 Try 失败时**不会**提交触发 Confirm，而是走 Cancel
4. **二阶段可靠性**：失败后写入 `WMD_ERRORTCC_IMAGE_T` + Kafka 告警 + 延迟自动重试（最多 3 线程队列 1000）
5. **状态机**：`REGISTER('P') → CONFIRM('C')` 或 `REGISTER('P') → CANCEL('R')`
6. **Kafka 旁路**：Try/Confirm/Cancel 报文都会发送 Kafka（`BypassKafkaManager`），用于监控和补偿
7. **分库支持**：通过 `dbDivName` 和 `WMD_RAC` 指定目标库执行二阶段，`checkWmdDbDiv` 保证同事务不跨库