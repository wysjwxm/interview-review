## 1.隔离级别

1. 四种隔离级别解决的问题
2. RR避免幻读的方式：MVCC+NEXT-KEY LOCK
3. 延伸-MVCC的实现原理：ReadView+隐藏字段+undo log
4. 延伸-当前读、快照读
5. 延伸-锁机制：for share读锁，for update和dml写锁



## 2.三大日志

> 是什么，有什么用，怎么用

#### undo log

1. 形式：记录撤销变更需要的信息，链式结构组织。Innodb有
2. 作用：保证事务的隔离性，控制事务中查询可见的数据版本

#### redo log

1. 作用：减少脏页刷盘减少IO；崩溃恢复
2. 形式：表空间,页号,页内偏移,旧字节,新字节。Innodb有
3. 落盘
   1. 实际是文件组，构成循环数组，通过write pos标明写入位置，checkpoint标明擦除位置（已入idb）
   2. 数据写入磁盘前，对应的redo log会先落盘
   3. 未commit也会落盘，通过有无commit的redolog判断一个事务是否应该被前滚（两阶段提交）
4. 刷盘时机
   1. 脏页刷盘（后台、内存不足、redolog满、关机）
   2. redo log刷盘（commit、redolog buffer满、内存满）

#### bin log

1. 作用：用来做数据的同步、备份。所有引擎都有
2. 形式：可配置是生成执行的sql-statement，还是填充参数的sql-row，还是混合存储-mixed（仅在右歧义时填充参数）。
3. 事务执行中，写入binlog cache，提交后写入binlog文件
4. 两阶段提交![image-20260831223624961](/Users/wenguang/Library/Application Support/typora-user-images/image-20260831223624961.png)
   1. 事务执行中写redolog是prepare阶段，事务提交，写入binlog，redolog改成commit阶段
   2. 场景1：重启时发现redolog还在prepare & 无binlog，弃用redolog
   3. 场景2：重启时发现redolog还在prepare & 有binlog，前滚redolog（解决设置为commit时失败的场景）



#### 数据迁移

> 先拿一个一致性快照做全量，再持续追增量，最后在差值极小的瞬间切换。

1. 快照同步（可以靠rr下的事务快照）+增量同步（目标库当成从库做同步、外部工具）
2. 双写一段时间，再将旧数据迁移到新库。校验完没问题再将读流量切到新库
   1. 代码解决冲突（如if contains update else insert）
   2. 双写如何保证同时成功（需要补偿机制）



## 3.索引

#### B+树

1. 每个页16k，若全存键可以存上千个（在该页尾保存Page Directory，每几条实际记录选哨兵放进目录槽，先对目录槽做二分，再对实际区间做二分）



#### 执行计划

1. select_type
   1. subquery：select或where出现的子查询
   2. derived：from出现的子查询
2. type
   1. system, constant
   2. eq_ref, ref
   3. range
   4. index, all
3. rows：估算出找到记录所需要读取的行数
4. filtered：join用rows*filtered估算驱动表行数
5. extra
   1. using filesort：server还需聚合，超出sort_buffer_size还需借助临时文件
   2. using temporary：创建临时文件



## 4.性能优化

#### 深度分页

1. limit M offset N == limit N, M
2. offset N 会查N+M条，然后丢弃N条，N大时会扫描很多记录
3. 通过主键游标解决 ` WHERE id > 100000 ORDER BY id LIMIT 10` 

#### 连表查询

1. left join，左表会作驱动表（右表可为空），可通过`/*+JOIN_ORDER(A,B)*/`控制连接顺序
2. Index Nested-Loop Join
3. Block Nested-Loop Join
4. Hash Join, 将驱动表编程hash表，被驱动表去hash表匹配数据





## 5.架构

#### Server层

1. 连接器—分析器—优化器—执行器（登录，词法语法，执行计划索引、操作引擎权限控制）
2. 跨存储引擎的功能（存储过程、触发器、视图、函数、binlog）
3. 做orderby、join、where...

![56380eb361c1d7baf6239bc386280719](/Users/wenguang/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_itzdl6t7qgkj22_2050/temp/RWTemp/2026-09/56380eb361c1d7baf6239bc386280719.jpg)

#### 执行流程

1. DQL：鉴权，词法语法，执行优化，鉴权，执行器调用，数据处理
2. DML：走一遍DQL，写redolog buffer，写undolog，写BufferPool（Write-Ahead Logging），redolog-prepare落盘，binlog落盘，redolog-commit落盘

