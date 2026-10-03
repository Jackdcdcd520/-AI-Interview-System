import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Button, Card, Rate, Input, Tag, Spin, Empty, Space, Modal, Collapse,
  message, Popconfirm, Divider, Alert, Descriptions, Tooltip,
  AutoComplete, Switch,
} from 'antd'
import {
  LeftOutlined, RightOutlined, SaveOutlined, ReloadOutlined,
  RobotOutlined, FileTextOutlined, UserOutlined, PlusCircleOutlined,
  CheckCircleOutlined, ExpandOutlined, DownloadOutlined,
  TeamOutlined, InfoCircleOutlined, LockOutlined,
} from '@ant-design/icons'
import api from '../api'
import CandHighlight from '../components/CandHighlight'

// 「锁定面试官」的本地记忆 key —— 存在浏览器里，多台设备各自记住自己的面试官
const LOCK_INTERVIEWER_KEY = 'interview.lockInterviewer'

// 评分维度：优先用后端下发的 data.dimensions（config/settings.py 的 SCORE_DIMENSIONS），
// 这里只是后端不可用时的兜底副本，改配置后无需改前端。
const FALLBACK_DIMENSIONS = [
  { key: 'character', label: '性格沟通', weight: 0.30 },
  { key: 'ability', label: '工作能力', weight: 0.30 },
  { key: 'potential', label: '发展潜力', weight: 0.20 },
  { key: 'overall', label: '综合评分', weight: 0.20, highlight: true },
]

// highlight=true 的维度（综合评分）在界面上做放大显示
function normalizeDims(raw) {
  if (!Array.isArray(raw) || !raw.length) return FALLBACK_DIMENSIONS
  const out = raw
    .filter((d) => d && d.key)
    .map((d) => ({
      key: d.key,
      label: d.label || d.key,
      weight: typeof d.weight === 'number' ? d.weight : 0,
      highlight: !!d.highlight,
    }))
  return out.length ? out : FALLBACK_DIMENSIONS
}

// ---- 六星等级评分 ----
// 每个维度用 0~6 颗星评级，星星映射到百分制分数（与后端 0~100 数据格式完全兼容）
const STAR_MAX = 6
export const STAR_SCORES = [0, 50, 60, 70, 80, 90, 100] // 下标 = 星数
const STAR_LABELS = ['', '待改进', '及格', '中等', '良好', '优秀', '卓越']
const STAR_TOOLTIPS = [
  '1 星 · 待改进（50 分）',
  '2 星 · 及格（60 分）',
  '3 星 · 中等（70 分）',
  '4 星 · 良好（80 分）',
  '5 星 · 优秀（90 分）',
  '6 星 · 卓越（100 分）',
]

function starsToScore(stars) {
  return STAR_SCORES[stars] ?? 0
}

// 已有分数（含历史滑杆数据）→ 最接近的星数
function scoreToStars(score) {
  if (typeof score !== 'number') return 0
  let best = 0
  let bestDiff = Infinity
  for (let i = 0; i <= STAR_MAX; i++) {
    const diff = Math.abs(score - STAR_SCORES[i])
    if (diff < bestDiff) {
      bestDiff = diff
      best = i
    }
  }
  return best
}

function calcTotal(scores, dims) {
  const hit = dims.filter((d) => scores[d.key] !== undefined && scores[d.key] !== null)
  if (!hit.length) return null
  const wsum = hit.reduce((s, d) => s + d.weight, 0)
  const raw = hit.reduce((s, d) => s + scores[d.key] * d.weight, 0)
  if (wsum <= 0) return null
  return Math.round((raw / wsum) * 100) / 100
}

function levelColor(level) {
  if (level === '强烈推荐') return 'red'
  if (level === '推荐') return 'orange'
  if (level === '待定') return 'blue'
  if (level === '不推荐') return 'default'
  return 'default'
}

export default function InterviewPage() {
  const { candidateId } = useParams()
  const navigate = useNavigate()
  const [msgApi, ctxHolder] = message.useMessage()

  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [dims, setDims] = useState(FALLBACK_DIMENSIONS)   // 评分维度（后端下发优先）
  const [scores, setScores] = useState({})
  const [comment, setComment] = useState('')
  const [interviewer, setInterviewer] = useState('')
  const [saving, setSaving] = useState(false)
  const [aiResult, setAiResult] = useState(null)
  const [resume, setResume] = useState(null)
  const [origPreview, setOrigPreview] = useState(null) // 原件预览分派结果（pdf/html/text）
  const [origLoading, setOrigLoading] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const [joint, setJoint] = useState(null)   // 联评综合评分（多面试官）
  const [interviewerOptions, setInterviewerOptions] = useState([])  // 历史面试官名单
  const [lockInterviewer, setLockInterviewer] = useState(
    () => {
      try {
        return localStorage.getItem(LOCK_INTERVIEWER_KEY) === '1'
      } catch {
        return false
      }
    }
  )
  // applyData 是 useCallback([])，用 ref 读取最新的锁定状态，避免闭包拿到旧值
  const lockRef = useRef(lockInterviewer)
  lockRef.current = lockInterviewer

  const total = calcTotal(scores, dims)
  const normalDims = dims.filter((d) => !d.highlight)
  const highlightDims = dims.filter((d) => d.highlight)

  // 点星回调：点回第 1 颗星再点一次 = 取消该维度评价
  const setDimStars = (key) => (val) =>
    setScores((s) => {
      const next = { ...s }
      if (!val) {
        delete next[key]
      } else {
        next[key] = starsToScore(val)
      }
      return next
    })

  const applyData = useCallback((d) => {
    setData(d)
    const ds = normalizeDims(d.dimensions)
    setDims(ds)
    if (d.empty) {
      setScores({})
      setComment('')
      return
    }
    const cur = d.current_interview || {}
    const sc = cur.scores && typeof cur.scores === 'object' ? cur.scores : {}
    // 只取已知维度的数值
    const clean = {}
    ds.forEach((dim) => {
      const v = sc[dim.key]
      if (typeof v === 'number') clean[dim.key] = v
    })
    setScores(clean)
    setComment(cur.comment || '')
    // 锁定面试官时：切候选人不再改动已选面试官（空值时仍带出记录里的默认值）
    setInterviewer((prev) =>
      lockRef.current && prev ? prev : (cur.interviewer || '')
    )
    setAiResult(
      cur.ai_summary || cur.ai_evaluation
        ? { summary: cur.ai_summary, evaluation: cur.ai_evaluation, provider: cur.ai_provider }
        : null
    )
  }, [])

  const load = useCallback(
    async (fn) => {
      setLoading(true)
      try {
        const d = fn ? await fn() : await api.current()
        applyData(d)
      } catch (e) {
        msgApi.error(e.message)
      } finally {
        setLoading(false)
      }
    },
    [applyData, msgApi]
  )

  useEffect(() => {
    if (candidateId) {
      load(() => api.goto(Number(candidateId)))
    } else {
      load(null)
    }
  }, [candidateId, load])

  // ---------------- 面试官名单（下拉选择） ----------------
  const loadInterviewers = useCallback(async () => {
    try {
      const r = await api.interviewers()
      setInterviewerOptions(r.items || [])
    } catch {
      setInterviewerOptions([])
    }
  }, [])

  useEffect(() => {
    loadInterviewers()
  }, [loadInterviewers])

  // 锁定开关：状态写进 localStorage，多台设备各自记住自己的面试官
  const toggleLockInterviewer = (val) => {
    setLockInterviewer(val)
    try {
      localStorage.setItem(LOCK_INTERVIEWER_KEY, val ? '1' : '0')
    } catch {
      /* 浏览器隐私模式下写入失败可忽略，仅本次会话生效 */
    }
    msgApi.info(
      val
        ? '已锁定面试官：切换候选人时保持为你现在填写的面试官。'
        : '已取消锁定：切换候选人时会显示该候选人记录里的面试官。'
    )
  }

  // 简历
  useEffect(() => {
    if (!data?.candidate?.id) {
      setResume(null)
      return
    }
    let alive = true
    api
      .getResume(data.candidate.id)
      .then((r) => alive && setResume(r))
      .catch(() => alive && setResume(null))
    return () => {
      alive = false
    }
  }, [data?.candidate?.id])

  const doNext = () => load(() => api.next())
  const doPrev = () => load(() => api.previous())

  // ---------------- 联评综合评分（多面试官平均） ----------------
  const refreshJoint = useCallback(async (candidateId) => {
    if (!candidateId) {
      setJoint(null)
      return
    }
    try {
      setJoint(await api.joint(candidateId))
    } catch {
      setJoint(null)
    }
  }, [])

  useEffect(() => {
    refreshJoint(data?.candidate?.id)
  }, [data?.candidate?.id, refreshJoint])

  // ---------------- 简历原件预览（Word→PDF / pdf / text 统一分派） ----------------
  const loadOriginal = useCallback(async (candidateId) => {
    setOrigLoading(true)
    try {
      const r = await api.resumePreview(candidateId)
      setOrigPreview(r)
    } catch {
      setOrigPreview(null)
    } finally {
      setOrigLoading(false)
    }
  }, [])

  // 切换候选人时清掉上一位的预览缓存，并自动加载原件预览
  useEffect(() => {
    const cid = data?.candidate?.id
    if (!cid) return
    setOrigPreview(null)
    loadOriginal(cid)
  }, [data?.candidate?.id, loadOriginal])

  const openBigPreview = async () => {
    const cid = data?.candidate?.id
    if (!cid) return
    setPreviewOpen(true)
    setPreviewData(null)
    setPreviewError('')
    setPreviewLoading(true)
    try {
      const r = await api.resumePreview(cid)
      setPreviewData(r)
    } catch (e) {
      setPreviewError(e.message)
    } finally {
      setPreviewLoading(false)
    }
  }

  const doSave = async (opts = {}) => {
    if (!data?.candidate?.id) return
    const filled = dims.filter((d) => scores[d.key] !== undefined)
    if (!filled.length) {
      msgApi.warning('请至少给一个维度打分后再保存。')
      return
    }
    setSaving(true)
    try {
      const r = await api.submitInterview({
        candidate_id: data.candidate.id,
        interviewer: interviewer || null,
        scores,
        comment: comment || null,
        generate_ai: opts.generateAi !== false,
      })
      setAiResult(
        r.ai && (r.ai.summary || r.ai.evaluation)
          ? { summary: r.ai.summary, evaluation: r.ai.evaluation, provider: r.ai.provider }
          : null
      )
      msgApi.success(
        `${r.is_update ? '已更新' : '已保存'} ${r.candidate_name} 第 ${r.round} 轮 — 总分 ${r.total_score}`
      )
      // 保存后刷新当前候选人数据（轮次与记录保持一致）
      const d = await api.current()
      applyData(d)
      refreshJoint(d?.candidate?.id)
      loadInterviewers()
      if (opts.thenNext) {
        await doNext()
      }
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  const doAdvance = async () => {
    if (!data?.candidate?.id) return
    try {
      const r = await api.advance(data.candidate.id)
      msgApi.success(r.message)
      applyData(r)
    } catch (e) {
      msgApi.error(e.message)
    }
  }

  const doAiEvaluate = async () => {
    if (!data?.candidate?.id) return
    setSaving(true)
    try {
      const r = await api.aiEvaluate(data.candidate.id)
      setAiResult({ summary: r.summary, evaluation: r.evaluation, provider: r.provider_used })
      msgApi.success(`AI 评估完成（provider: ${r.provider_used}）`)
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  const resetScores = () => {
    setScores({})
    setComment('')
    msgApi.info('已清空本次打分（未保存到后端）。')
  }

  if (loading && !data) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (data?.empty) {
    return (
      <Card>
        <Empty description="尚未加载到候选人数据">
          <div className="empty-hint" style={{ textAlign: 'left' }}>
            {data.message}
          </div>
        </Empty>
      </Card>
    )
  }

  const c = data?.candidate || {}
  const pos = data?.position || 0
  const tot = data?.total || 0
  const curRound = data?.current_round || 1
  const completedRounds = data?.completed_rounds || 0
  const resumeInfo = resume?.resume || data?.resume || {}
  const resumeExt = (resumeInfo.ext || '').toLowerCase()

  return (
    <div>
      {ctxHolder}

      {/* ---------------- 顶部导航条 ---------------- */}
      <Card size="small" style={{ marginBottom: 14 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <span className="order-badge">{pos} / {tot}</span>
          <CandHighlight name={c.name} studentNo={c.student_no} grade={c.grade} />
          <span style={{ color: '#a6a6a6', fontSize: 13 }}>
            {c.major || '专业未填'} · {c.position || '岗位未填'}
          </span>
          <Tag color="blue">第 {curRound} 轮进行中</Tag>
          {completedRounds > 0 && (
            <Tooltip title={`已完成的轮次：${(data.rounds_completed_list || []).join('、')}`}>
              <Tag icon={<CheckCircleOutlined />} color="green">
                已完成 {completedRounds} 轮
              </Tag>
            </Tooltip>
          )}

          <div style={{ flex: 1 }} />

          <Space>
            <Button
              icon={<LeftOutlined />}
              onClick={doPrev}
              disabled={!data?.has_prev}
            >
              上一位
            </Button>
            <Button
              type="primary"
              icon={<RightOutlined />}
              onClick={doNext}
              disabled={!data?.has_next}
            >
              下一位
            </Button>
          </Space>
        </div>
      </Card>

      {/* ---------------- 三栏主体 ---------------- */}
      <div className="interview-grid">
        {/* ============ 左：候选人信息（可折叠） + 简历大窗 ============ */}
        <div className="panel">
          <Collapse
            ghost
            size="small"
            className="info-collapse"
            items={[
              {
                key: 'info',
                label: <span><UserOutlined /> 候选人信息（点开收起）</span>,
                children: (
                  <Descriptions column={1} size="small" colon={false}
                    styles={{ label: { color: '#a6a6a6', width: 76 }, content: { fontSize: 13 } }}>
                    <Descriptions.Item label="姓名">{c.name || '-'}</Descriptions.Item>
                    <Descriptions.Item label="学号">{c.student_no || '-'}</Descriptions.Item>
                    <Descriptions.Item label="专业">{c.major || '-'}</Descriptions.Item>
                    <Descriptions.Item label="班级">{c.grade || '-'}</Descriptions.Item>
                    <Descriptions.Item label="应聘岗位">{c.position || '-'}</Descriptions.Item>
                    <Descriptions.Item label="手机">{c.phone || '-'}</Descriptions.Item>
                    <Descriptions.Item label="邮箱">{c.email || '-'}</Descriptions.Item>
                    <Descriptions.Item label="面试顺序">
                      第 {c.order_index || pos} 位
                    </Descriptions.Item>
                  </Descriptions>
                ),
              },
            ]}
          />

          <div className="panel-title" style={{ marginTop: 8 }}>
            <span><FileTextOutlined /> 简历{resumeInfo.found && (
              <span className="mono" style={{ marginLeft: 8, fontWeight: 400 }}>
                {resumeInfo.filename} ({Math.round((resumeInfo.size || 0) / 1024)} KB)
              </span>
            )}</span>
            {resumeInfo.found && (
              <Space size={6}>
                <Tooltip title="在弹出的大窗口中查看简历原件（PDF / Word）">
                  <Button size="small" icon={<ExpandOutlined />} onClick={openBigPreview}>
                    大窗预览
                  </Button>
                </Tooltip>
                <a href={api.resumeFileUrl(c.id)} target="_blank" rel="noreferrer">
                  <Button size="small" icon={<DownloadOutlined />}>下载</Button>
                </a>
              </Space>
            )}
          </div>

          {!resumeInfo.found ? (
            <div className="empty-hint">
              {resumeInfo.message ||
                `未在 E:\\InterviewSystem\\Resumes 找到 ${c.name} 的简历。`}
              <br />
              <span style={{ fontSize: 12 }}>
                可把简历文件（文件名含姓名）放入该目录后刷新页面。
                支持 PDF / DOCX / DOC / TXT / MD。
              </span>
            </div>
          ) : (
            resumeExt === '.pdf' ? (
              <iframe
                className="resume-pdf resume-pdf-lg"
                src={api.resumeFileUrl(c.id)}
                title="简历 PDF"
              />
            ) : origLoading ? (
              <div style={{ textAlign: 'center', padding: 48 }}>
                <Spin />
                <div style={{ marginTop: 12, color: '#888' }}>
                  正在调用本机 Word 转换为 PDF（首次约 3~8 秒，之后秒开）…
                </div>
              </div>
            ) : origPreview?.kind === 'pdf' ? (
              <iframe
                className="resume-pdf resume-pdf-lg"
                src={origPreview.url}
                title="简历原件（已转 PDF）"
              />
            ) : origPreview?.kind === 'html' ? (
              <div
                className="resume-paper resume-paper-lg"
                dangerouslySetInnerHTML={{ __html: origPreview.html }}
              />
            ) : origPreview?.kind === 'text' ? (
              <div className="resume-box resume-box-lg">
                {origPreview.text || '（未抽取到文字内容）'}
              </div>
            ) : (
              <div className="empty-hint">
                {origPreview?.message
                  || '该格式暂不支持在线预览，可点「下载」查看。'}
              </div>
            )
          )}
        </div>

        {/* ============ 中：评分（核心） ============ */}
        <div className="panel">
          <div className="panel-title">
            <span>面试评分 · 第 {curRound} 轮</span>
            <Space size={6}>
              <Tooltip title="清空当前未保存的打分">
                <Button size="small" icon={<ReloadOutlined />} onClick={resetScores}>
                  清空
                </Button>
              </Tooltip>
              <Popconfirm
                title={`开启第 ${curRound + 1} 轮面试？`}
                description="当前轮将结束并保留，之后打分写入新一轮。"
                onConfirm={doAdvance}
                okText="确认开启"
                cancelText="取消"
              >
                <Tooltip title={`需要第二轮面试时使用`}>
                  <Button size="small" icon={<PlusCircleOutlined />}>
                    开新一轮
                  </Button>
                </Tooltip>
              </Popconfirm>
            </Space>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 10,
              margin: '4px 0 14px',
            }}
          >
            <span
              className={`score-total ${
                total === null ? 'low' : total >= 75 ? 'high' : total >= 60 ? 'mid' : 'low'
              }`}
            >
              {total === null ? '--' : total}
            </span>
            <span style={{ color: '#a6a6a6', fontSize: 13 }}>
              / 100 加权总分
              {total !== null && (
                <Tag color={levelColor(
                  total >= 85 ? '强烈推荐' : total >= 75 ? '推荐' : total >= 60 ? '待定' : '不推荐'
                )} style={{ marginLeft: 8 }}>
                  {total >= 85 ? '强烈推荐' : total >= 75 ? '推荐' : total >= 60 ? '待定' : '不推荐'}
                </Tag>
              )}
            </span>
          </div>

          <div className="ai-note" style={{ marginBottom: 12 }}>
            六星等级评分：每维 0~6 星，对应 0 / 50 / 60 / 70 / 80 / 90 / 100 分。
            再点一次当前第 1 颗星可取消该维度评价。
          </div>

          {normalDims.map((d) => {
            const v = scores[d.key]
            const stars = scoreToStars(v)
            return (
              <div key={d.key} className="star-dim-row" style={{ marginBottom: 12 }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'baseline',
                    fontSize: 13,
                    marginBottom: 4,
                  }}
                >
                  <span>
                    {d.label}
                    <span className="weight-tag">{Math.round(d.weight * 100)}%</span>
                  </span>
                  <span
                    style={{
                      fontVariantNumeric: 'tabular-nums',
                      fontWeight: 600,
                      color: v === undefined ? '#666' : '#e8e8e8',
                    }}
                  >
                    {v === undefined
                      ? '未评'
                      : `${v} 分 · ${STAR_LABELS[stars]}`}
                  </span>
                </div>
                <Rate
                  count={STAR_MAX}
                  value={stars}
                  tooltips={STAR_TOOLTIPS}
                  onChange={setDimStars(d.key)}
                />
              </div>
            )
          })}

          {/* ---- 综合评分：放大显示（面试官总体印象分） ---- */}
          {highlightDims.map((d) => {
            const v = scores[d.key]
            const stars = scoreToStars(v)
            const lvl = v === undefined
              ? null
              : v >= 85 ? '强烈推荐' : v >= 75 ? '推荐' : v >= 60 ? '待定' : '不推荐'
            return (
              <div key={d.key} className="star-dim-row star-dim-row--hl">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: 1 }}>
                      {d.label}
                    </span>
                    <span className="weight-tag">{Math.round(d.weight * 100)}%</span>
                    <Tag color="gold" style={{ margin: 0 }}>总体印象分</Tag>
                  </span>
                  <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                    <span
                      style={{
                        fontSize: 34,
                        fontWeight: 800,
                        lineHeight: 1,
                        fontVariantNumeric: 'tabular-nums',
                        color: v === undefined ? '#555' : '#faad14',
                      }}
                    >
                      {v === undefined ? '--' : v}
                    </span>
                    <span style={{ fontSize: 13, color: '#a6a6a6' }}>分</span>
                  </span>
                </div>

                <Rate
                  className="rate-hl"
                  count={STAR_MAX}
                  value={stars}
                  tooltips={STAR_TOOLTIPS}
                  onChange={setDimStars(d.key)}
                />

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    fontSize: 12,
                    color: '#a6a6a6',
                    marginTop: 2,
                  }}
                >
                  <span>面试官对该候选人的总体印象，独立于上面三项评价</span>
                  <span>
                    {v === undefined ? (
                      '未评'
                    ) : (
                      <>
                        <span style={{ color: '#c0c0c0' }}>{STAR_LABELS[stars]}</span>
                        {lvl && (
                          <Tag color={levelColor(lvl)} style={{ marginLeft: 6 }}>{lvl}</Tag>
                        )}
                      </>
                    )}
                  </span>
                </div>
              </div>
            )
          })}

          <Divider style={{ margin: '8px 0 12px' }} />

          <div style={{ marginBottom: 10 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 4,
              }}
            >
              <span style={{ fontSize: 13, color: '#a6a6a6' }}>
                面试官
                {lockInterviewer && interviewer && (
                  <Tag color="gold" style={{ marginLeft: 6 }}>已锁定</Tag>
                )}
              </span>
              <Tooltip
                title={
                  lockInterviewer
                    ? '已锁定：点「下一位」/「上一位」时面试官保持不变。关掉即可恢复自动带出。'
                    : '开启后，选好面试官再切下一位候选人时，这一栏不会再变（推荐多端各自开启）。'
                }
              >
                <Space size={6} style={{ cursor: 'pointer' }}>
                  <LockOutlined
                    style={{ fontSize: 12, color: lockInterviewer ? '#faad14' : '#666' }}
                  />
                  <span style={{ fontSize: 12, color: '#a6a6a6' }}>锁定</span>
                  <Switch
                    size="small"
                    checked={lockInterviewer}
                    onChange={toggleLockInterviewer}
                  />
                </Space>
              </Tooltip>
            </div>
            <AutoComplete
              size="small"
              className="interviewer-select"
              style={{ width: '100%' }}
              value={interviewer}
              options={interviewerOptions.map((n) => ({ value: n }))}
              onChange={(v) => setInterviewer(v || '')}
              placeholder="例如：王老师（可从历史名单中选，也可直接输入）"
              allowClear
              filterOption={(input, option) =>
                String(option?.value || '')
                  .toLowerCase()
                  .includes(String(input || '').toLowerCase())
              }
            />
            <div style={{ fontSize: 12, color: '#666', marginTop: 4, lineHeight: 1.6 }}>
              {lockInterviewer
                ? `已锁定为「${interviewer || '未填写'}」：切上一位 / 下一位都不会变。`
                : '未锁定：切换候选人时会带出该候选人记录里的面试官。'}
            </div>
          </div>

          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 13, color: '#a6a6a6', marginBottom: 4 }}>评价 / 备注</div>
            <Input.TextArea
              rows={4}
              placeholder="记录候选人的表现、亮点与不足……（系统会保存这条评价）"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </div>

          <Space style={{ width: '100%' }} direction="vertical" size={8}>
            <Space style={{ width: '100%' }}>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                onClick={() => doSave({ generateAi: true })}
              >
                保存（含 AI 总结）
              </Button>
              <Popconfirm
                title="保存并进入下一位？"
                onConfirm={() => doSave({ generateAi: true, thenNext: true })}
                okText="保存并下一位"
                cancelText="取消"
              >
                <Button icon={<SaveOutlined />} loading={saving}>
                  保存并下一位
                </Button>
              </Popconfirm>
            </Space>
            <Button
              icon={<RobotOutlined />}
              onClick={doAiEvaluate}
              loading={saving}
              block
            >
              单独触发 AI 智能评估
            </Button>
          </Space>

          <div className="ai-note">
            同一轮重复保存只会<strong>更新</strong>当前记录，不会产生重复面试记录。
            如需第二轮面试，请先点「开新一轮」。
          </div>
        </div>

        {/* ============ 右：联评综合评分 + AI 结果 ============ */}
        <div className="panel">
          <div className="panel-title">
            <span><TeamOutlined /> 联评综合评分</span>
            <Tooltip title={joint?.rule || '联评综合分 = 各面试官平均分的平均'}>
              <InfoCircleOutlined style={{ color: '#a6a6a6' }} />
            </Tooltip>
          </div>

          {!joint?.has_data ? (
            <div className="empty-hint" style={{ marginBottom: 12 }}>
              还没有面试官打分。保存评分后，这里会显示多位面试官评价的平均成绩。
            </div>
          ) : (
            <>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  gap: 10,
                  marginBottom: 6,
                }}
              >
                <span
                  className={`score-total ${
                    joint.joint_score >= 75 ? 'high' : joint.joint_score >= 60 ? 'mid' : 'low'
                  }`}
                >
                  {joint.joint_score}
                </span>
                <span style={{ color: '#a6a6a6', fontSize: 13 }}>
                  / 100 联评综合分
                  <Tag color={levelColor(joint.joint_level)} style={{ marginLeft: 8 }}>
                    {joint.joint_level}
                  </Tag>
                </span>
              </div>

              <div style={{ fontSize: 12, color: '#a6a6a6', marginBottom: 10 }}>
                {joint.interviewer_count} 位面试官 · 共 {joint.rounds_considered} 轮评价
                {' · '}
                <span
                  style={{
                    color:
                      joint.consensus === '分歧较大'
                        ? '#ff7875'
                        : joint.consensus === '高度一致'
                          ? '#52c41a'
                          : '#a6a6a6',
                  }}
                >
                  {joint.consensus}
                  {joint.std !== null && ` (σ=${joint.std})`}
                </span>
                {joint.interviewer_count > 1 && (
                  <>
                    {' · '}最高 {joint.interviewers[0].avg_score} / 最低{' '}
                    {joint.interviewers[joint.interviewers.length - 1].avg_score}
                  </>
                )}
              </div>

              {joint.interviewers.map((iv) => (
                <div key={iv.interviewer} style={{ marginBottom: 8 }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 12,
                      marginBottom: 3,
                    }}
                  >
                    <span>
                      <UserOutlined style={{ marginRight: 4, color: '#666' }} />
                      {iv.interviewer}
                      <span style={{ color: '#666', marginLeft: 6 }}>
                        {iv.rounds} 轮
                      </span>
                    </span>
                    <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                      {iv.avg_score}
                      <span style={{ color: '#666', fontWeight: 400, marginLeft: 4 }}>
                        （{iv.scores.join(' / ')}）
                      </span>
                    </span>
                  </div>
                  <div
                    style={{
                      height: 6,
                      background: '#1f1f1f',
                      borderRadius: 3,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${Math.max(2, Math.min(100, iv.avg_score))}%`,
                        height: '100%',
                        background:
                          iv.avg_score >= 85
                            ? '#ff4d4f'
                            : iv.avg_score >= 75
                              ? '#ffa940'
                              : iv.avg_score >= 60
                                ? '#4096ff'
                                : '#595959',
                      }}
                    />
                  </div>
                </div>
              ))}

              {joint.interviewer_count === 1 && (
                <div style={{ fontSize: 12, color: '#666', lineHeight: 1.7 }}>
                  目前只有 1 位面试官的评价，联评分即该面试官的平均分；
                  当第 2、3 位面试官也打分后，这里会自动合并为多人的平均成绩。
                </div>
              )}
            </>
          )}

          <Divider style={{ margin: '14px 0' }} />

          <div className="panel-title">
            <span><RobotOutlined /> AI 总结与评估</span>
            {aiResult?.provider && (
              <Tag color={aiResult.provider === 'mock' ? 'orange' : 'blue'}>
                {aiResult.provider}
              </Tag>
            )}
          </div>

          {!aiResult ? (
            <div className="empty-hint">
              还没有 AI 结果。
              <br />
              点击「保存（含 AI 总结）」或「单独触发 AI 智能评估」后显示在这里。
              <br />
              <br />
              当前默认使用 <strong>mock</strong> provider（无需 API Key）。
              在 <span className="mono">config/settings.json</span> 里配置 deepseek 后可切换为真实大模型。
            </div>
          ) : (
            <>
              {aiResult.summary && (
                <>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>面试总结</div>
                  <div
                    style={{
                      fontSize: 13,
                      lineHeight: 1.8,
                      background: '#101010',
                      border: '1px solid #303030',
                      borderRadius: 8,
                      padding: 10,
                      marginBottom: 14,
                    }}
                  >
                    {aiResult.summary}
                  </div>
                </>
              )}

              {aiResult.evaluation && (
                <>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                    智能评估
                    {aiResult.evaluation.level && (
                      <Tag color={levelColor(aiResult.evaluation.level)} style={{ marginLeft: 6 }}>
                        {aiResult.evaluation.level}
                      </Tag>
                    )}
                  </div>

                  {aiResult.evaluation.summary && (
                    <div style={{ fontSize: 13, color: '#c0c0c0', marginBottom: 10 }}>
                      {aiResult.evaluation.summary}
                    </div>
                  )}

                  <div style={{ fontSize: 13, marginBottom: 6 }}>
                    <span style={{ color: '#a6a6a6' }}>优势：</span>
                    {(aiResult.evaluation.strengths || []).length
                      ? aiResult.evaluation.strengths.map((s, i) => (
                          <div key={i} style={{ paddingLeft: 12, color: '#ff7875' }}>
                            + {s}
                          </div>
                        ))
                      : '（无）'}
                  </div>

                  <div style={{ fontSize: 13, marginBottom: 6 }}>
                    <span style={{ color: '#a6a6a6' }}>短板：</span>
                    {(aiResult.evaluation.weaknesses || []).length
                      ? aiResult.evaluation.weaknesses.map((s, i) => (
                          <div key={i} style={{ paddingLeft: 12, color: '#95de64' }}>
                            - {s}
                          </div>
                        ))
                      : '（无）'}
                  </div>

                  {aiResult.evaluation.suggestion && (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginTop: 10, fontSize: 13 }}
                      message="建议"
                      description={aiResult.evaluation.suggestion}
                    />
                  )}

                  {aiResult.evaluation.dimension_detail && (
                    <>
                      <Divider style={{ margin: '14px 0 8px' }} />
                      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                        维度加权明细
                      </div>
                      {aiResult.evaluation.dimension_detail.map((d) => (
                        <div className="dim-row" key={d.key}>
                          <span className="dim-label">
                            {d.label}
                            <span className="weight-tag">
                              {Math.round((d.weight || 0) * 100)}%
                            </span>
                          </span>
                          <span style={{ color: '#a6a6a6', fontSize: 12 }}>
                            加权 {d.weighted ?? '-'}
                          </span>
                          <span className="dim-score">{d.score ?? '-'}</span>
                        </div>
                      ))}
                    </>
                  )}

                  {aiResult.evaluation.ai_fallback && (
                    <div className="ai-note">{aiResult.evaluation.ai_fallback}</div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* ---------------- 简历大窗预览 Modal ---------------- */}
      <Modal
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        title={
          <span>
            简历原件预览 · {c.name}
            {previewData?.filename && (
              <span className="mono" style={{ marginLeft: 10, fontWeight: 400, fontSize: 12 }}>
                {previewData.filename}
                {previewData.converted ? '（由 Word 转换为 PDF）' : ''}
              </span>
            )}
          </span>
        }
        width="94vw"
        style={{ top: 24 }}
        footer={null}
        styles={{ body: { height: '78vh', overflow: 'auto', padding: 0 } }}
      >
        {previewLoading ? (
          <div style={{ textAlign: 'center', padding: 80 }}>
            <Spin size="large" />
            <div style={{ marginTop: 12, color: '#a6a6a6' }}>
              正在加载简历原件…（.doc 首次转换需数秒）
            </div>
          </div>
        ) : previewError ? (
          <div style={{ padding: 24 }}>
            <Alert type="error" showIcon message="预览加载失败" description={previewError} />
          </div>
        ) : !previewData ? null : previewData.kind === 'pdf' ? (
          <iframe
            src={previewData.url}
            title="简历 PDF 预览"
            style={{ width: '100%', height: '78vh', border: 'none', background: '#525659' }}
          />
        ) : previewData.kind === 'html' ? (
          <div style={{ padding: 24, display: 'flex', justifyContent: 'center', background: '#262626', minHeight: '78vh' }}>
            <div
              className="resume-paper"
              style={{ width: 'min(860px, 100%)', minHeight: '74vh' }}
              dangerouslySetInnerHTML={{ __html: previewData.html }}
            />
          </div>
        ) : previewData.kind === 'text' ? (
          <div className="resume-box" style={{ maxHeight: 'none', minHeight: '78vh', borderRadius: 0, border: 'none' }}>
            {previewData.text || '（未抽取到文字内容）'}
          </div>
        ) : (
          <div style={{ padding: 24 }}>
            <Alert
              type="warning"
              showIcon
              message="无法内嵌预览"
              description={previewData.message || '该文件格式暂不支持在线预览。'}
              action={
                <a href={api.resumeFileUrl(c.id)} target="_blank" rel="noreferrer">
                  <Button size="small" icon={<DownloadOutlined />}>下载原件</Button>
                </a>
              }
            />
            {previewData.text && (
              <div className="resume-box" style={{ marginTop: 16 }}>
                {previewData.text}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
