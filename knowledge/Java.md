## HashMap 

##### 重写hashCode&equals

1. 用自定义类做key需要重写hashCode&equals：等值判断方式决定，第一步：用 hashCode 定位桶  →  桶下标 = hash & (n-1) 第二步：在桶里用 equals 逐个比对  →  找到匹配的节点

##### ConcurrentHashMap

1. put
   1. 桶为空时用 **CAS** 写入，无锁。cas失败，等下一轮循环重新判定走CAS还是sync
   2. 桶非空时用 **synchronized (桶头节点)** 加锁，只锁这一个桶
2. get无锁：Node.val, Node.next都声明为vialote保证可见性
3. size：弱一致性，因为读size做累加过程中其他线程还可以并发写 Cell /baseCount



## 锁

##### CAS

1. `CAS(V, exptV, newV): if(V==exptV) V=newV`  注意，方法中的V为内存地址，if中的V为内存地址对应值
2. CAS比锁快：CAS-CPU指令，sync操作系统介入
3. ABA问题，若业务关心则使用版本号
4. CAS失败后读取新值做exptV，自旋重试：`while (!CAS(V, exptV, newV)) exptV = V`
5. 自旋开销：竞争非常激烈，CPU 会空转，适合冲突低、操作短（如更新内存变量）



##### ReentrantLock

1. 按请求顺序排队获取。新线程可以和队头抢锁。



##### synchronized渐进

1. **偏向锁**：只有一个线程访问时，不 CAS，偏向（我属于线程 A，线程 A 再来时直接放行）（高版本jdk默认关）
2. **轻量级锁**：有轻度竞争时，线程自旋 CAS 尝试获取，不挂起
3. **重量级锁**：竞争激烈或自旋超过次数，升级为操作系统互斥量，线程挂起



##### 可重入

1. 锁内部记录了**持有线程**和**重入次数**，同一个线程再来就次数 +1，退出时次数 -1，减到 0 才真正释放



##### volatile

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



##### AQS

1. AbstractQueuedSynchronizer。实现排队、挂起、唤醒，子类只需定制：怎么算抢到、抢到怎么释放
2. volatile state，由实现类决定
   1. ReentrantLock：0 = 锁空闲，>0 = 被占用且记录重入次数
   2. CountDownLatch：还需要 countDown 几次
3. CLH 变种双向队列：CLH 是隐式单向链表，纯自旋；AQS 是显式双向链表，自旋几次后挂起线程（park），被唤醒再自旋
4. CAS





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

