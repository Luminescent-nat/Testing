/**
 * GENERATED MOCK - 仅隔离开发/测试，禁止用于生产/联调
 *
 * 本文件由 scripts/generate-contract-mocks.mjs 从 docs/contracts/*.md 的已确认 JSON 样例
 * 确定性生成，请勿手工修改。当前环境无 mock-api 工具，此文件为已记录的偏差产物，
 * 需用户确认后方可用于真实联调替代；正式联调必须切换到真实后端接口。
 *
 * source-digest: sha256:ea3fc258efa219d1816ff2dcf2bf1c01b9e95a47fa97892b56f23835e2722d74
 * entries: 24
 */

/** @type {Array<{method: string, path: string, source: string, requests: Array<object>, responses: Array<object>}>} */
export const CONTRACT_MOCK_ENTRIES = [
  {
    method: 'GET',
    path: '/api/v1/devices',
    source: 'docs/contracts/device-authorization-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "success",
        "data": {
          "items": [
            {
              "id": 1,
              "serial_number": "A133P-01",
              "model": "A133P",
              "brand": "allwinner",
              "android_version": "10.1",
              "sdk_version": "29",
              "cpu_abi": "arm64-v8a",
              "resolution": null,
              "battery_level": null,
              "board": "a133p",
              "hardware": "sun50iw10",
              "ddr_info": null,
              "emmc_info": null,
              "wifi_chip": null,
              "bt_chip": null,
              "eth_interfaces": [],
              "features": [],
              "status": "online",
              "owner_id": 2,
              "pc_identifier": "pc-a",
              "version": 1,
              "last_seen_at": "2026-11-09T08:00:00Z",
              "created_at": "2026-11-09T07:00:00Z"
            }
          ],
          "total": 1,
          "page": 1,
          "page_size": 20
        }
      },
      {
        "code": "VALIDATION_ERROR",
        "message": "查询参数不合法",
        "details": {
          "field": "page_size",
          "reason": "必须位于1～100"
        }
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/devices/{serial}',
    source: 'docs/contracts/device-authorization-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": "FORBIDDEN",
        "message": "无权限访问此设备",
        "details": {
          "field": "serial",
          "reason": "owner或PC分组不满足"
        }
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/device-discoveries',
    source: 'docs/contracts/device-authorization-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 201,
        "message": "设备发现完成",
        "data": {
          "items": [],
          "total": 0,
          "owner_unchanged": true
        }
      },
      {
        "code": "SERVICE_UNAVAILABLE",
        "message": "ADB发现失败",
        "details": {
          "reason": "ADB调用未成功，设备状态未批量变更"
        }
      }
    ]
  },
  {
    method: 'PATCH',
    path: '/api/v1/devices/{serial}',
    source: 'docs/contracts/device-authorization-v1.0.md',
    requests: [
      {
        "owner_id": 2,
        "pc_identifier": "pc-a",
        "version": 1
      }
    ],
    responses: [
      {
        "code": 200,
        "message": "设备归属已更新",
        "data": {
          "id": 1,
          "serial_number": "A133P-01",
          "model": "A133P",
          "brand": "allwinner",
          "android_version": "10.1",
          "sdk_version": "29",
          "cpu_abi": "arm64-v8a",
          "resolution": null,
          "battery_level": null,
          "board": "a133p",
          "hardware": "sun50iw10",
          "ddr_info": null,
          "emmc_info": null,
          "wifi_chip": null,
          "bt_chip": null,
          "eth_interfaces": [],
          "features": [],
          "status": "online",
          "owner_id": 2,
          "pc_identifier": "pc-a",
          "version": 2,
          "last_seen_at": "2026-11-09T08:00:00Z",
          "created_at": "2026-11-09T07:00:00Z"
        }
      },
      {
        "code": "CONFLICT",
        "message": "设备已被其他操作更新",
        "details": {
          "field": "version",
          "reason": "请重新读取后提交"
        }
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/knowledge/{id}/conversion-previews',
    source: 'docs/contracts/knowledge-rules-v1.0.md',
    requests: [
      {
        "target_type": "rule",
        "extra_hint": "提取网络延迟规则"
      }
    ],
    responses: [
      {
        "code": 201,
        "message": "转换预览已生成",
        "data": {
          "target_type": "rule",
          "preview_data": {
            "target_item_name": "网络延迟",
            "conditional_rules": {
              "conditions": [
                {
                  "source": "regex:latency=([0-9.]+)",
                  "operator": "gte",
                  "target": "100",
                  "tolerance": "0%",
                  "on_fail": "延迟低于下限"
                }
              ],
              "returncode_zero": true
            }
          },
          "has_llm": false,
          "validation": {
            "valid": true,
            "errors": []
          }
        }
      },
      {
        "code": "VALIDATION_ERROR",
        "message": "转换预览参数不合法",
        "details": {
          "field": "preview_data.conditional_rules.conditions",
          "reason": "至少一个条件且不能使用空规则"
        }
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/knowledge/{id}/conversions',
    source: 'docs/contracts/knowledge-rules-v1.0.md',
    requests: [
      {
        "target_type": "rule",
        "preview_data": {
          "target_item_id": 12,
          "conditional_rules": {
            "conditions": [
              {
                "source": "regex:latency=([0-9.]+)",
                "operator": "gte",
                "target": "100",
                "tolerance": "0%",
                "on_fail": "延迟低于下限"
              }
            ],
            "returncode_zero": true
          }
        }
      }
    ],
    responses: [
      {
        "code": 201,
        "message": "测试资产转换成功",
        "data": {
          "asset_type": "rule",
          "detail": {
            "target_item_id": 12,
            "target_item_name": "网络延迟",
            "rules_count": 1
          }
        }
      },
      {
        "code": "VALIDATION_ERROR",
        "message": "转换数据不合法",
        "details": {
          "field": "preview_data.conditional_rules.conditions.0.operator",
          "reason": "未知操作符"
        }
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/reports/{task_id}',
    source: 'docs/contracts/reporting-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "success",
        "data": {
          "report_version": "2.0",
          "report_id": "RPT-20261109-101",
          "task_id": 101,
          "task_name": "基础测试",
          "task_status": "completed",
          "task_result": "passed",
          "created_at": "2026-11-09T08:00:00Z",
          "completed_at": "2026-11-09T08:01:00Z",
          "total_duration_seconds": 0,
          "executor": {
            "user_id": 2,
            "username": "operator",
            "role": "user"
          },
          "device": {
            "serial_number": "A133P-01",
            "model": "A133P",
            "brand": "allwinner",
            "android_version": "10.1",
            "cpu_abi": "arm64-v8a",
            "board": "a133p"
          },
          "summary": {
            "total_items": 2,
            "pass": 1,
            "fail": 0,
            "skip": 1,
            "error": 0,
            "timeout": 0,
            "pass_rate": 100
          },
          "results": [
            {
              "item_id": 12,
              "item_name": "网络",
              "module_name": "WIFI",
              "status": "pass",
              "execution_time": 0,
              "reason": null,
              "extracted_data": {
                "latency": 0
              },
              "output_summary": "ok",
              "actual_result": {
                "latency": 0
              },
              "verdict_basis": "断言满足",
              "suggested_fix": null
            }
          ],
          "execution_context": {
            "evidence_status": "current",
            "commit": "627e5f28a16772816d474694f5a96c0a79b4a611",
            "environment": "test",
            "execution_mode": "mock",
            "device_serial": null,
            "board": null,
            "captured_at": "2026-11-09T08:01:00Z"
          },
          "coverage": {
            "static_item_ids": [],
            "real_item_ids": [],
            "skips": [
              {
                "item_id": "T1-06",
                "reason": "无外设，未执行实机项"
              }
            ]
          }
        }
      },
      {
        "code": "FORBIDDEN",
        "message": "无权限查看报告",
        "details": {}
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/reports/{task_id}/exports',
    source: 'docs/contracts/reporting-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": "VALIDATION_ERROR",
        "message": "导出格式不合法",
        "details": {
          "field": "format",
          "reason": "仅支持json/html/markdown/excel/word"
        }
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/report-exports',
    source: 'docs/contracts/reporting-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": "VALIDATION_ERROR",
        "message": "批量导出参数不合法",
        "details": {
          "field": "task_ids",
          "reason": "至少一个不重复任务ID"
        }
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/dashboard/stats',
    source: 'docs/contracts/reporting-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "success",
        "data": {
          "today": {
            "tasks": 0,
            "completed": 0,
            "passed": 0,
            "failed": 0,
            "no_result": 0,
            "execution_failed": 0,
            "cancelled": 0,
            "pass_rate": null
          },
          "running_tasks": 0,
          "pending_tasks": 0,
          "devices": {
            "total": 0,
            "online": 0
          }
        }
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/reports/stats/trend',
    source: 'docs/contracts/reporting-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "success",
        "data": {
          "days": 1,
          "series": [
            {
              "date": "2026-11-09",
              "total": 0,
              "passed": 0,
              "failed": 0,
              "no_result": 0,
              "execution_failed": 0,
              "cancelled": 0,
              "pass_rate": null
            }
          ]
        }
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/reports/stats/by-module',
    source: 'docs/contracts/reporting-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "success",
        "data": {
          "items": []
        }
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/tasks',
    source: 'docs/contracts/task-execution-v1.0.md',
    requests: [
      {
        "device_serial": "A133P-01",
        "name": "基础测试",
        "item_ids": [
          12,
          13
        ],
        "custom_parameters": {
          "12": {
            "target": "8.8.8.8",
            "count": 0
          }
        },
        "schedule_type": "immediate",
        "scheduled_time": null
      }
    ],
    responses: [
      {
        "code": 201,
        "message": "任务创建成功",
        "data": {
          "id": 101,
          "name": "基础测试",
          "device_serial": "A133P-01",
          "task_kind": "instance",
          "status": "pending",
          "result": null,
          "total_items": 2,
          "completed_items": 0,
          "counts": {
            "pass": 0,
            "fail": 0,
            "skip": 0,
            "error": 0,
            "timeout": 0
          },
          "progress_percent": 0,
          "pass_rate": null,
          "schedule_type": "immediate",
          "scheduled_time": null,
          "next_run_at": null,
          "template_id": null,
          "scheduled_for": null,
          "item_snapshot_status": "complete",
          "started_at": null,
          "completed_at": null,
          "created_at": "2026-11-09T08:00:00Z"
        }
      },
      {
        "code": "VALIDATION_ERROR",
        "message": "任务参数不合法",
        "details": {
          "field": "custom_parameters.12.count",
          "reason": "不允许嵌套对象、数组或null"
        }
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/tasks',
    source: 'docs/contracts/task-execution-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "success",
        "data": {
          "items": [],
          "total": 0,
          "page": 1,
          "page_size": 20
        }
      },
      {
        "code": "VALIDATION_ERROR",
        "message": "查询参数不合法",
        "details": {
          "field": "status",
          "reason": "不支持的任务状态"
        }
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/tasks/{id}',
    source: 'docs/contracts/task-execution-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": "FORBIDDEN",
        "message": "无权限查看此任务",
        "details": {}
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/tasks/{id}/records',
    source: 'docs/contracts/task-execution-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "success",
        "data": {
          "items": [],
          "total": 0,
          "page": 1,
          "page_size": 20
        }
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/tasks/{id}/cancellations',
    source: 'docs/contracts/task-execution-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": "CONFLICT",
        "message": "当前状态不可取消",
        "details": {
          "field": "status",
          "reason": "completed任务不可取消"
        }
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/tasks/{id}/reruns',
    source: 'docs/contracts/task-execution-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": "CONFLICT",
        "message": "当前任务不可重跑",
        "details": {
          "reason": "没有fail/error/timeout记录"
        }
      }
    ]
  },
  {
    method: 'DELETE',
    path: '/api/v1/tasks/{id}',
    source: 'docs/contracts/task-execution-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "任务已删除",
        "data": {
          "id": 101,
          "deleted": true,
          "artifacts": "retained"
        }
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/auth/registrations',
    source: 'docs/contracts/user-administration-v1.0.md',
    requests: [
      {
        "username": "first-admin",
        "password": "change-me-now",
        "pc_identifier": "pc-admin"
      }
    ],
    responses: [
      {
        "code": 201,
        "message": "首管理员创建成功",
        "data": {
          "id": 1,
          "username": "first-admin",
          "role": "admin",
          "status": "active",
          "pc_identifier": "pc-admin",
          "last_login_at": null,
          "created_at": "2026-11-09T08:00:00Z"
        }
      },
      {
        "code": "FORBIDDEN",
        "message": "系统已完成初始化",
        "details": {}
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/auth/sessions',
    source: 'docs/contracts/user-administration-v1.0.md',
    requests: [
      {
        "username": "operator",
        "password": "user-pass",
        "pc_identifier": "pc-a"
      }
    ],
    responses: [
      {
        "code": 201,
        "message": "登录成功",
        "data": {
          "access_token": "eyJhbGciOiJIUzI1NiJ9.example",
          "token_type": "bearer",
          "expires_in": 86400,
          "user": {
            "id": 2,
            "username": "operator",
            "role": "user",
            "status": "active",
            "pc_identifier": "pc-a",
            "last_login_at": "2026-11-09T08:00:00Z",
            "created_at": "2026-11-09T07:00:00Z"
          }
        }
      },
      {
        "code": "FORBIDDEN",
        "message": "用户已被禁用",
        "details": {}
      }
    ]
  },
  {
    method: 'POST',
    path: '/api/v1/users',
    source: 'docs/contracts/user-administration-v1.0.md',
    requests: [
      {
        "username": "operator",
        "password": "user-pass",
        "role": "user",
        "status": "active",
        "pc_identifier": "pc-a"
      }
    ],
    responses: [
      {
        "code": 201,
        "message": "用户创建成功",
        "data": {
          "id": 2,
          "username": "operator",
          "role": "user",
          "status": "active",
          "pc_identifier": "pc-a",
          "last_login_at": null,
          "created_at": "2026-11-09T08:00:00Z"
        }
      },
      {
        "code": "CONFLICT",
        "message": "用户名已存在",
        "details": {
          "field": "username",
          "reason": "唯一约束冲突"
        }
      }
    ]
  },
  {
    method: 'GET',
    path: '/api/v1/users',
    source: 'docs/contracts/user-administration-v1.0.md',
    requests: [
    ],
    responses: [
      {
        "code": 200,
        "message": "success",
        "data": {
          "items": [],
          "total": 0,
          "page": 1,
          "page_size": 20
        }
      },
      {
        "code": "FORBIDDEN",
        "message": "需要管理员权限",
        "details": {}
      }
    ]
  },
  {
    method: 'PATCH',
    path: '/api/v1/users/{id}',
    source: 'docs/contracts/user-administration-v1.0.md',
    requests: [
      {
        "status": "disabled"
      }
    ],
    responses: [
      {
        "code": 200,
        "message": "用户已更新",
        "data": {
          "id": 2,
          "username": "operator",
          "role": "user",
          "status": "disabled",
          "pc_identifier": "pc-a",
          "last_login_at": "2026-11-09T08:00:00Z",
          "created_at": "2026-11-09T07:00:00Z"
        }
      },
      {
        "code": "CONFLICT",
        "message": "管理员状态变更冲突",
        "details": {
          "reason": "不能禁用或降级最后一个active管理员"
        }
      }
    ]
  }
]

/**
 * 将契约模板路径（含 {param}）编译为精确路径匹配正则。
 * @param {string} pattern 契约模板路径
 * @returns {RegExp} 匹配实际路径的正则
 */
const compilePathPattern = (pattern) => {
  const source = pattern
    .split('/')
    .map((segment) =>
      /^\{[a-zA-Z0-9_]+\}$/.test(segment)
        ? '[^/]+'
        : segment.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    )
    .join('/')
  return new RegExp(`^${source}$`)
}

/**
 * 归一化实际请求路径：去掉查询串，补全 /api/v1 前缀。
 * @param {string} url 请求 URL（可含查询串）
 * @returns {string} 归一化路径
 */
export const normalizeMockPath = (url) => {
  const noQuery = String(url || '').split('?')[0]
  if (noQuery.startsWith('/api/v1')) return noQuery
  return `/api/v1${noQuery.startsWith('/') ? noQuery : `/${noQuery}`}`
}

/**
 * 按方法与路径查找契约 mock 条目（仅隔离开发/测试使用）。
 * @param {string} method HTTP 方法
 * @param {string} url 请求 URL
 * @returns {object|null} 命中的条目
 */
export const findContractMock = (method, url) => {
  const upperMethod = String(method || 'get').toUpperCase()
  const actualPath = normalizeMockPath(url)
  return (
    CONTRACT_MOCK_ENTRIES.find(
      (entry) => entry.method === upperMethod && compilePathPattern(entry.path).test(actualPath)
    ) || null
  )
}

/**
 * 取该接口的首个 2xx 响应样例；无 2xx 时回退首个响应样例。
 * @param {string} method HTTP 方法
 * @param {string} url 请求 URL
 * @returns {object|null} 响应样例
 */
export const getContractMockResponse = (method, url) => {
  const entry = findContractMock(method, url)
  if (!entry || entry.responses.length === 0) return null
  const success = entry.responses.find(
    (item) => typeof item.code === 'number' && item.code >= 200 && item.code < 300
  )
  return success || entry.responses[0]
}

/**
 * 生成 axios 自定义 adapter，供隔离开发/测试注入使用。
 * 未命中样例时返回带 MOCK_NOT_FOUND 的 404 响应，便于发现契约覆盖缺口。
 * @returns {(config: object) => Promise<object>} axios adapter
 */
export const createContractMockAdapter = () => {
  return async (config) => {
    const sample = getContractMockResponse(config.method, config.url)
    if (sample) {
      const status = typeof sample.code === 'number' ? sample.code : 200
      return {
        data: sample,
        status,
        statusText: 'OK',
        headers: {},
        config,
        request: null
      }
    }
    const notFound = {
      code: 'MOCK_NOT_FOUND',
      message: '契约 mock 未覆盖该请求',
      details: { field: 'path', reason: normalizeMockPath(config.url) }
    }
    return { data: notFound, status: 404, statusText: 'Not Found', headers: {}, config, request: null }
  }
}
