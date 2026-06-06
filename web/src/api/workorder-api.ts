// 工单 API 封装：负责单个工单查询和工单状态流转。

import {
  API_PATHS,
  type UpdateWorkOrderStatusRequestData,
  type WorkOrderData,
} from '@/lib/api-contracts'
import { httpClient } from '@/lib/http-client'

// 按工单 ID 查询工单详情。
export function getWorkOrder(workOrderId: string) {
  return httpClient.get<WorkOrderData>(API_PATHS.workOrders.detail(workOrderId))
}

// 更新工单状态、负责人或关闭说明。
export function updateWorkOrderStatus(workOrderId: string, data: UpdateWorkOrderStatusRequestData) {
  return httpClient.patch<WorkOrderData>(API_PATHS.workOrders.status(workOrderId), data)
}
