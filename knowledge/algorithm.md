## DP

### 一、背包问题

##### 1.01背包

> 有容量capcity，n个物品，重量记为weight[i]，价值为value[i]。体积至多capicity时，如何选可以获得最大价值的物品组合

```python
# 使用回溯，操作-枚举第i个物品选或不选，加入背包剩余容量c，问题-从前i个物品求最大价值，子问题-从前i-1个物品求出最大价值
def zero-one-knapsack(capicity: int, w: list[int], v: list[int]):
  
  def dfs(i, c):
    if i < 0:
      return 0
    if c < w[i]:
      return dfs(i-1, c)
    else:
      return max(dfs(i-1, c), dfs(i-1, c-w[i])) 
  
  dfs(len(w) - 1, capicity)
```



##### 2.完全背包

> 有容量capcity，n种物品，每个物品可重复选，重量记为weight[i]，价值为value[i]。体积至多capicity时如何选可以获得最大价值的物品组合

```python
# 使用回溯，操作-枚举第i种物品选或不选，加入背包剩余容量c，问题-从前i种物品求最大价值，子问题-从前i-1种物品求出最大价值
# 对比01，选了以后，物品索引不往前推，表示第i个可以重复选至不想选
def unbounded-knapsack(capicity: int, w: list[int], v: list[int]):
  
  def dfs(i, c):
    if i < 0:
      return 0
    if c < w[i]:
      return dfs(i, c)
    else:
      return max(dfs(i-1, c), dfs(i, c-w[i])) 
    
  dfs(len(w) - 1, capicity)
```



##### 3.变形

1. 求取变形：最大价值和、最小价值和、方案数----修改递推式：max、min、+
2. 条件变形：至多、至少、恰好capicity----修改边界判断：增加if c==0...



### 二、LCS

#### 1.求操作

> 输入 old code 和 new code 两个字符串数组，希望输出一组：keep / delete / add，使 old code 最终变成 new code

1. 计算 old, new 的 LCS，得到公共对齐序列
2. 双指针 i (old 下标), j (new 下标)，从 0 遍历
3. 如果 old [i] == new [j] 并且这个元素属于 LCS（对齐点）  输出 `keep old[i]`；i+=1，j+=1
4. 否则：  向前看：如果 old [i] 不在下一个待对齐的 LCS 元素：   输出 `delete old[i]`；i +=1  否则   输出 `add new[j]`；j +=1
5. 边界：i 走完，j 还有剩余：全部 add   j 走完，i 还有剩余：全部 delete