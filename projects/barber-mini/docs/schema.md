# 集合与字段（云开发）

> 字段名即契约；`customerType` 是统计维度，**必须用固定枚举**，不许自由文本。

## barbers
```json
{ "_id": "b1", "openid": "oX...", "name": "阿明", "avatar": "",
  "status": "idle|busy|rest", "currentOrderId": null, "autoAccept": false,
  "serviceItems": [], "createdAt": 0 }
```

## serviceItems
```json
{ "_id": "s1", "barberId": "b1", "name": "剪发", "defaultDuration": 40,
  "price": 38, "icon": "scissors", "description": "", "sortOrder": 1 }
```

## orders（唯一可写的业务集合）
```json
{ "_id": "o1", "barberId": "b1", "customerOpenid": "oY...", "customerName": "小王",
  "customerType": "woman|elder|child|man", "serviceItemId": "s1", "serviceName": "剪发",
  "duration": 40, "priority": 0, "status": "pending",
  "appointmentTime": 0, "actualStartTime": 0, "actualEndTime": 0,
  "isPrepaid": false, "prepaidAmount": 0, "createdAt": 0, "updatedAt": 0 }
```

**`priority` 真源 = `isPrepaid`**：预付款 0、已预约 1、现场 2。两端**只能读 priority、不许各自算**（要算就调 `shared/priority.js`）。

## 索引建议
- `orders`: `(barberId, status)`、`(barberId, appointmentTime)`、`(customerOpenid, status)`
- `serviceItems`: `(barberId, sortOrder)`

## 权限（云开发安全规则）
- `orders` / `barbers` / `serviceItems`：**所有客户端写 = false**（只读自己的、或按 `barberId` 读公开状态）；
  一切写经云函数（云函数用管理员权限）。
