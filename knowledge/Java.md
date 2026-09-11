## JVM

### 1. 内存模型

<img src="/Users/wenguang/Projects/interview-review/knowledge/assets/image-20260911220451212.png" alt="image-20260911220451212" style="zoom: 67%;" />

1. 私有空间
   1. 虚拟机栈：由栈帧构成
   2. 本地方法栈
   3. 程序计数器：控制分支执行、保存当前执行位置
2. 堆
   1. 分新生代（eden+survivor）、老年代（old generation），随着经历垃圾回收次数而升级存储区
   2. 包括对象实例（对象头(包含Mark Word)、实例数据、对齐填充）、数组信息、字符串常量池
3. 本地内存
   1. 元空间
   2. 直接内存

### 2. 线程

1. 六个生命状态<img src="/Users/wenguang/Projects/interview-review/knowledge/assets/image-20260911231411122.png" alt="image-20260911231411122" style="zoom:50%;" />
   1. NEW: 初始状态，线程被创建出来但没有被调用 `start()`。
   2. RUNNABLE: 运行状态，线程被调用了 `start()` 等待运行的状态。
   3. BLOCKED：阻塞状态，需要等待锁释放。
   4. WAITING：等待状态，表示该线程需要等待其他线程做出一些特定动作（通知或中断）。
   5. TIMED_WAITING：超时等待状态，可以在指定的时间后自行返回而不是像 WAITING 那样一直等待。
   6. TERMINATED：终止状态，表示该线程已经运行完毕。





## 容器

### 1. HashMap 

#### 1. 重写hashCode&equals

1. 用自定义类做key需要重写hashCode&equals：等值判断方式决定，第一步：用 hashCode 定位桶  →  桶下标 = hash & (n-1) 第二步：在桶里用 equals 逐个比对  →  找到匹配的节点

#### 2. ConcurrentHashMap

1. put
   1. 桶为空时用 **CAS** 写入，无锁。cas失败，等下一轮循环重新判定走CAS还是sync
   2. 桶非空时用 **synchronized (桶头节点)** 加锁，只锁这一个桶
2. get无锁：Node.val, Node.next都声明为vialote保证可见性
3. size：弱一致性，因为读size做累加过程中其他线程还可以并发写 Cell /baseCount



### 2. 阻塞队列

1. 使用notFull和notEmpty两个Condition（队列）
2. put时队列满则将线程放到notFull去等待，put成功后唤醒notEmpty
3. take时队列空则将线程放到notEmpty去等待，take成功后唤醒notFull



## 锁

### 1. CAS

1. `CAS(V, exptV, newV): if(V==exptV) V=newV`  注意，方法中的V为内存地址，if中的V为内存地址对应值
2. CAS比锁快：CAS-CPU指令，sync操作系统介入
3. ABA问题，若业务关心则使用版本号
4. CAS失败后读取新值做exptV，自旋重试：`while (!CAS(V, exptV, newV)) exptV = V`
5. 自旋开销：竞争非常激烈，CPU 会空转，适合冲突低、操作短（如更新内存变量）



### 2. AQS

#### 1. 内部实现

1. AbstractQueuedSynchronizer。实现排队、挂起、唤醒，子类只需定制：怎么算抢到、抢到怎么释放
2. volatile state，由实现类决定
   1. ReentrantLock：0 = 锁空闲，>0 = 被占用且记录重入次数
   2. CountDownLatch：state表还需要 countDown 几次
   3. Semaphore：控制同时获取一资源的线程数量，state表还可获得许可的线程数
3. CLH 变种双向队列：CLH 是隐式单向链表，纯自旋；AQS 是显式双向链表，自旋几次后挂起线程（park），被唤醒再自旋
4. CAS



#### 2. ReentrantLock

1. 优于synchronized
   1. 公平锁
   2. 可中断
   3. trylock
   4. condotion



### 3. synchronized

#### 1. 字节码

1. 通过monitorenter获取锁，通过锁状态判断执行逻辑
2. 通过monitorexit释放锁（正常和异常都会释放）



#### 2. 锁升级

1. **偏向锁**：Mark Word 记录线程ID，若是同一线程，不CAS设置MW（高版本jdk默认关）
2. **轻量级锁**：有轻度竞争时，线程自旋 CAS 尝试获取，不挂起
   1. 交替持锁，无并行竞争
   2. CAS抢锁：修改MarkWord。将Mark Word放入栈的LockRecord，将锁对象头的Mark Word换成指向栈中lockrecord的指针，以判断是哪个线程
   3. CAS释放锁：修改MarkWord为LockRecord里保存的Displaced Mark Word
   4. CAS抢锁失败
      1. 同一线程重入，再创建lockrecord，靠lockrecord数量实现重入控制
      2. 不同线程，自选重试（自适应自选，即退避重试），多次自旋拿不到会锁升级
3. **重量级锁**：竞争激烈或自旋超过次数，升级为操作系统互斥量，线程挂起
   1. 锁对象头的指针开辟的ObjectMonitor，通过Monitor判断是哪个线程
   2. 等待队列包括以下
      1. entrylist双向链表，其他队列迁移到entrylist再进行锁资源获取
      2. waitset双向链表（wait放入，notify移到entrylist）
   3. owner表示当前占用资源的线程
   4. count占用次数



#### 3. Monitor

1. 抢锁，owner为空，设置owner，锁重入则count++
2. 抢不到锁，入队，调用原语park挂起线程 交出cpu
3. 释放锁，count为0时，清空owner，唤醒EntryList的线程来竞争锁（而非持有资源，可能被i新线程抢走，所以非公平）



#### 4. 修饰方法

1. 进入方法时争抢锁对象，若是实例方法抢实例的锁，若是类方法抢class的锁







### 4. volatile

1. 写：线程改的是自己工作内存的副本，什么时候刷回主内存是不确定的。修改变量后立即刷回主内存，并让其他 CPU 核心上这个变量的缓存行失效。

2. 读：从主内存读

3. 指令重排，若线程A做21，1还没做，线程B判断已初始化去取配置，报错

   1. ```java
      // 线程A
      config = loadConfig();  // 加载配置
      initialized = true;     // 标记初始化完成
      
      // 线程B
      if (initialized) {
          use(config);  // 可能拿到 null！
      }
      ```

   2. 通过内存屏障

      1. volatile 写之前的所有操作，必须在 volatile 写之前完成
      2. volatile 读之后的所有操作，必须在 volatile 读之后开始



### 5. ThreadLocal

1. TODO



### 6.ThreadPool

1. TODO





## 基础

### 1. BigDecimal

1. TODO





## 代码

1. ConcurrentHashMap


```java
final V putVal(K key, V value, boolean onlyIfAbsent) {
    int hash = spread(key.hashCode());   // 扰动计算 hash
    for (Node<K,V>[] tab = table;;) {    // 自旋循环
        int i = (n - 1) & hash;          // 定位桶下标
        Node<K,V> f = tabAt(tab, i);     // 拿到桶头节点
        
        if (f == null) {
            // 桶为空 → CAS 直接放新节点，无锁
            if (casTabAt(tab, i, null, new Node<>(hash, key, value)))
                break;                   // CAS 成功就结束
        } else {
            synchronized (f) {           // 桶非空 → 锁桶头节点
                // 遍历链表/红黑树，找到 key 就覆盖，找不到就尾插
                // 和 HashMap 逻辑一致
            }
        }
    }
    addCount(1L, binCount);              // 元素计数 +1，可能触发扩容
}
```

2. ReentrantLock

```java
// 这五个方法 AQS 里默认抛 UnsupportedOperationException
protected boolean tryAcquire(int arg)          // 尝试独占获取
protected boolean tryRelease(int arg)          // 尝试独占释放
protected int tryAcquireShared(int arg)        // 尝试共享获取
protected boolean tryReleaseShared(int arg)    // 尝试共享释放
protected boolean isHeldExclusively()          // 是否被当前线程独占
  
// 非公平锁的 tryAcquire
final boolean tryAcquire(int acquires) {
    int c = getState();
    if (c == 0) {
        if (compareAndSetState(0, acquires)) {  // 直接 CAS 抢，不管队列
            setExclusiveOwnerThread(Thread.currentThread());
            return true;
        }
    } else if (getExclusiveOwnerThread() == Thread.currentThread()) {
        setState(c + acquires);  // 可重入
        return true;
    }
    return false;  // 抢不到，AQS 负责让你入队
}
```

