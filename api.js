/**
 * API 客户端 —— 前端唯一与后端通信的出口。
 *
 * 关键约束：所有请求都走相对路径 `/api/...`，由 Vite 代理转发到后端。
 * 因此「切换后端地址 / 端口」只需要改 vite.config.js，前端组件完全不用动；
 * 「切换 AI 实现（mock ↔ deepseek）」后端自己处理，前端同样零改动。
 */

const API_BASE = '/api'

async function request(path, { method = 'GET', body, params } = {}) {
  let url = `${API_BASE}${path}`
  if (params) {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, v)
    })
    const s = qs.toString()
    if (s) url += `?${s}`
  }

  const init = { method, headers: {} }
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch(url, init)
  } catch (err) {
    // 网络层错误（后端没启动 / 端口不通）→ 抛出可读信息，页面显示提示而不是白屏
    throw new Error(
      `无法连接后端（${url}）。请确认后端已启动：scripts\\start_backend.bat`
    )
  }

  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { raw: text }
    }
  }

  if (!res.ok) {
    const detail =
      (data && (data.detail || data.message || data.error)) ||
      `HTTP ${res.status}`
    const e = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    e.status = res.status
    e.payload = data
    throw e
  }
  return data
}

export const api = {
  // ---------------- 系统 ----------------
  health: () => request('/health'),
  statistics: () => request('/summary/statistics'),

  // ---------------- 候选人 ----------------
  listCandidates: (params) => request('/candidates', { params }),
  getCandidate: (id) => request(`/candidates/${id}`),
  getResume: (id) => request(`/candidates/${id}/resume`),
  resumeFileUrl: (id) => `${API_BASE}/candidates/${id}/resume/file`,
  /** 大窗预览分派：pdf→url / html→html / text→text / unsupported→提示 */
  resumePreview: (id) => request(`/candidates/${id}/resume/preview`),
  /** .doc 经 Word/WPS 转换出的 PDF（inline） */
  resumeConvertedUrl: (id) => `${API_BASE}/candidates/${id}/resume/converted`,
  extractResume: (id, useAi = true) =>
    request(`/candidates/${id}/resume/extract`, { method: 'POST', params: { use_ai: useAi } }),
  candidateInterviews: (id) => request(`/candidates/${id}/interviews`),
  /** 联评综合评分：多面试官评价的平均成绩 */
  joint: (id) => request(`/candidates/${id}/joint`),
  /** 从面试顺序表同步候选人名单（新增/更新 + 重扫简历标记） */
  importFromOrder: () => request('/candidates/import-from-order', { method: 'POST' }),

  // ---------------- 面试流程 ----------------
  current: () => request('/interview/current'),
  next: () => request('/interview/next'),
  previous: () => request('/interview/previous'),
  goto: (id) => request(`/interview/goto/${id}`, { method: 'POST' }),
  resetPointer: () => request('/interview/reset', { method: 'POST' }),
  /** 历史面试官名单（去重）—— 面试官栏下拉选择用 */
  interviewers: () => request('/interview/interviewers'),
  /** 显式开启新一轮面试（普通保存不会自动开新轮） */
  advance: (id) => request(`/interview/advance/${id}`, { method: 'POST' }),
  submitInterview: (payload) =>
    request('/interviews', { method: 'POST', body: payload }),
  getInterview: (id) => request(`/interviews/${id}`),

  // ---------------- 结果汇总 ----------------
  /**
   * 结果汇总。params 支持：
   *   sort: order|total|joint|custom|rounds|name|dim:<维度key>|iv:<面试官名>
   *   weights / interviewer_weights: 对象，会序列化为 JSON 传给后端（可选覆盖）
   */
  results: ({ weights, interviewer_weights, ...rest } = {}) =>
    request('/results', {
      params: {
        ...rest,
        ...(weights ? { weights: JSON.stringify(weights) } : {}),
        ...(interviewer_weights
          ? { interviewer_weights: JSON.stringify(interviewer_weights) }
          : {}),
      },
    }),
  resultDetail: (id) => request(`/results/${id}`),
  /** 联评综合分排行榜 */
  jointRanking: (params) => request('/summary/joint', { params }),

  // ---------------- 评分权重（人工设定） ----------------
  getWeights: () => request('/settings/weights'),
  setDimensionWeights: (weights) =>
    request('/settings/weights/dimensions', { method: 'POST', body: { weights } }),
  resetDimensionWeights: () =>
    request('/settings/weights/dimensions', { method: 'DELETE' }),
  setInterviewerWeights: (weights) =>
    request('/settings/weights/interviewers', { method: 'POST', body: { weights } }),
  resetInterviewerWeights: () =>
    request('/settings/weights/interviewers', { method: 'DELETE' }),

  // ---------------- AI ----------------
  aiStatus: () => request('/ai/status'),
  aiEvaluate: (id, round) =>
    request(`/ai/evaluate/${id}`, { method: 'POST', params: round ? { round } : undefined }),
}

export default api
