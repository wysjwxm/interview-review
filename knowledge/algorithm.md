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