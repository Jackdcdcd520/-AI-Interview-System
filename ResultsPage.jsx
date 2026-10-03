import { useEffect, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Tag, Button, Space, Row, Col, Statistic, Segmented, Spin, Empty, message,
  Tooltip, Select, Modal, InputNumber, Slider, Tabs, Divider, Progress, Alert,
} from 'antd'
import {
  TrophyOutlined, ArrowUpOutlined, ArrowDownOutlined, EyeOutlined,
  PlayCircleOutlined, ReloadOutlined, SettingOutlined, FilterOutlined,
  UserOutlined, TeamOutlined,
} from '@ant-design/icons'
import api from '../api'
import CandHighlight from '../components/CandHighlight'

const LEVEL_COLOR = {
  强烈推荐: 'red',
  推荐: 'orange',
  待定: 'blue',
  不推荐: 'default',
  未评分: 'default',
}

// 评分维度：优先用后端下发的 data.dimensions（config/settings.py 的 SCORE_DIMENSIONS），
// 这里只是后端不可用时的兜底副本。
const FALLBACK_DIMENSIONS = [
  { key: 'character', label: '性格沟通', weight: 0.30 },
  { key: 'ability', label: '工作能力', weight: 0.30 },
  { key: 'potential', label: '发展潜力', weight: 0.20 },
  { key: 'overall', label: '综合评分', weight: 0.20, highlight: true },
]

function normalizeDims(raw, labels, defaults) {
  if (!Array.isArray(raw) || !raw.length) {
    // 退化路径：用 weights.dimensions 的 key 顺序 + labels 拼出来
    const keys = labels ? Object.keys(labels) : []
    if (!keys.length) return FALLBACK_DIMENSIONS
    return keys.map((k) => ({
      key: k,
      label: labels[k] || k,
      default: typeof defaults?.[k] === 'number' ? defaults[k] : 0,
      highlight: false,
    }))
  }
  return raw
    .filter((d) => d && d.key)
    .map((d) => ({
      key: d.key,
      label: d.label || d.key,
      default: typeof d.weight === 'number' ? d.weight : 0,
      highlight: !!d.highlight,
    }))
}

const BASE_SORTS = [
  { label: '按面试顺序', value: 'order' },
  { label: '按最高得分', value: 'total' },
  { label: '按联评综合分', value: 'joint' },
  { label: '按加权分', value: 'custom' },   // 仅当自定义维度权重生效时出现
  { label: '按已完成轮次', value: 'rounds' },
  { label: '按姓名', value: 'name' },
]

function scoreColor(v) {
  if (v === null || v === undefined) return '#666'
  if (v >= 85) return '#ff4d4f'
  if (v >= 75) return '#ffa940'
  if (v >= 60) return '#4096ff'
  return '#8c8c8c'
}

export default function ResultsPage() {
  const navigate = useNavigate()
  const [msgApi, holder] = message.useMessage()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  // 排序：常规排序 / 按单个维度 / 按单个面试官 —— 三者互斥
  const [segSort, setSegSort] = useState('order')
  const [dimSort, setDimSort] = useState(null)
  const [ivSort, setIvSort] = useState(null)
  const [desc, setDesc] = useState(true)

  // 权重设置弹窗
  const [weightsOpen, setWeightsOpen] = useState(false)
  const [dimDraft, setDimDraft] = useState({})
  const [ivDraft, setIvDraft] = useState({})
  const [savingWeights, setSavingWeights] = useState(false)

  const sort = dimSort ? `dim:${dimSort}` : ivSort ? `iv:${ivSort}` : segSort

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.results({ sort, desc })
      setData(d)
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [sort, desc, msgApi])

  useEffect(() => {
    load()
  }, [load])

  const st = data?.statistics || {}
  const dimCustomized = !!data?.weights?.dimensions_customized
  const ivCustomized = !!data?.weights?.interviewers_customized
  // 后端给的「百分比口径」（合计 100），无论默认权重是 0.30 还是手填 60 都统一展示
  const dimPercent = data?.weights?.dimension_percent || {}
  const ivPercent = data?.weights?.interviewer_percent || {}
  const ivOptions = data?.interviewer_options || []

  // 维度列表由后端下发（含 label / 默认权重 / 是否放大），改配置无需改前端
  const DIMENSIONS = useMemo(
    () =>
      normalizeDims(
        data?.dimensions,
        data?.weights?.dimension_labels,
        data?.weights?.dimension_defaults,
      ),
    [data],
  )

  const sorts = useMemo(
    () => (dimCustomized ? BASE_SORTS : BASE_SORTS.filter((s) => s.value !== 'custom')),
    [dimCustomized]
  )

  // 打开弹窗时，用后端已生效的权重初始化草稿（统一换算成百分比）
  useEffect(() => {
    if (!weightsOpen) return
    const d = {}
    DIMENSIONS.forEach((x) => {
      const w = dimPercent[x.key]
      d[x.key] = typeof w === 'number' ? Math.round(w) : Math.round(x.default * 100)
    })
    setDimDraft(d)
    const m = {}
    ivOptions.forEach((n) => {
      const w = ivPercent[n]
      m[n] = typeof w === 'number' ? Math.round(w) : 1
    })
    setIvDraft(m)
  }, [weightsOpen, data])   // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- 排序控件互斥切换 ----------
  const onSegChange = (v) => {
    setSegSort(v)
    setDimSort(null)
    setIvSort(null)
  }
  const onDimChange = (v) => {
    setDimSort(v || null)
    if (v) setIvSort(null)
  }
  const onIvChange = (v) => {
    setIvSort(v || null)
    if (v) setDimSort(null)
  }

  // ---------- 权重应用 / 恢复默认 ----------
  const applyWeights = async () => {
    setSavingWeights(true)
    try {
      await api.setDimensionWeights(dimDraft)
      const names = Object.keys(ivDraft)
      if (names.length) {
        await api.setInterviewerWeights(ivDraft)
      } else {
        await api.resetInterviewerWeights()
      }
      msgApi.success('权重已保存，汇总结果按新权重重算。')
      setWeightsOpen(false)
      await load()
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setSavingWeights(false)
    }
  }

  const resetWeights = async () => {
    setSavingWeights(true)
    try {
      await api.resetDimensionWeights()
      await api.resetInterviewerWeights()
      msgApi.success('已恢复系统默认权重。')
      setWeightsOpen(false)
      setSegSort('order')
      setDimSort(null)
      setIvSort(null)
      await load()
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setSavingWeights(false)
    }
  }

  const showRankMedal =
    desc && (['total', 'joint', 'custom'].includes(sort) ||
      sort.startsWith('dim:') || sort.startsWith('iv:'))

  const columns = [
    {
      title: '名次',
      width: 62,
      align: 'center',
      render: (_, __, i) => {
        if (showRankMedal) {
          const medal = i === 0 ? '#ffd700' : i === 1 ? '#c0c0c0' : i === 2 ? '#cd7f32' : '#666'
          return (
            <span style={{ fontWeight: 700, color: i < 3 ? medal : '#666' }}>
              {i + 1}
            </span>
          )
        }
        return <span style={{ color: '#666' }}>{i + 1}</span>
      },
    },
    {
      title: '顺序',
      dataIndex: 'order_index',
      width: 64,
      render: (v) => <span className="order-badge">{v ?? '-'}</span>,
    },
    {
      title: '姓名 / 学号 / 班级',
      dataIndex: 'name',
      width: 250,
      render: (_, r) => (
        <CandHighlight
          size="sm"
          name={r.name}
          studentNo={r.student_no}
          grade={r.grade}
        />
      ),
    },
    { title: '专业', dataIndex: 'major', ellipsis: true },
    { title: '应聘岗位', dataIndex: 'position', width: 108 },
    {
      title: '轮次',
      dataIndex: 'rounds',
      width: 66,
      align: 'center',
      render: (v) => (v ? <Tag color="blue">{v}</Tag> : <span style={{ color: '#666' }}>0</span>),
    },
    {
      title: '最高得分',
      dataIndex: 'best_score',
      width: 92,
      align: 'right',
      sorter: (a, b) => (a.best_score || -1) - (b.best_score || -1),
      render: (v) => (
        <span
          style={{
            color: v === null ? '#666' : '#ff4d4f',
            fontWeight: 600,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {v === null ? '--' : v}
        </span>
      ),
    },
    {
      title: '最近得分',
      dataIndex: 'latest_score',
      width: 88,
      align: 'right',
      render: (v) => <span style={{ color: '#a6a6a6' }}>{v === null ? '--' : v}</span>,
    },
    {
      title: '平均分',
      dataIndex: 'avg_score',
      width: 80,
      align: 'right',
      render: (v) => <span style={{ color: '#a6a6a6' }}>{v === null ? '--' : v}</span>,
    },
    {
      title: '面试官',
      dataIndex: 'interviewer_count',
      width: 76,
      align: 'center',
      render: (v, r) =>
        v ? (
          <Tooltip title={(r.interviewers || []).join('、')}>
            <Tag color={v > 1 ? 'purple' : 'default'}>{v} 人</Tag>
          </Tooltip>
        ) : (
          <span style={{ color: '#666' }}>-</span>
        ),
    },
    {
      title: ivCustomized ? '联评综合分（已加权）' : '联评综合分',
      dataIndex: 'joint_score',
      width: ivCustomized ? 148 : 108,
      align: 'right',
      sorter: (a, b) => (a.joint_score || -1) - (b.joint_score || -1),
      render: (v, r) => (
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>
          <span style={{ color: v === null ? '#666' : '#ff4d4f', fontWeight: 600 }}>
            {v === null ? '--' : v}
          </span>
          {v !== null && r.interviewer_count > 1 && (
            <Tooltip
              title={
                `${r.interviewer_count} 位面试官的平均成绩 · ${r.joint_consensus || ''}` +
                (ivCustomized
                  ? ` · 已按面试官权重加权（等权参考：${r.joint_score_equal}）`
                  : '')
              }
            >
              <span style={{ color: '#666', fontSize: 11, marginLeft: 4 }}>
                ({r.interviewer_count}人)
              </span>
            </Tooltip>
          )}
        </span>
      ),
    },
  ]

  // 自定义维度权重生效时，插入「加权分」列（放在联评前）
  if (dimCustomized) {
    columns.splice(8, 0, {
      title: (
        <Tooltip title="按人工设定的维度权重重算的加权总分（只算已评维度，自动归一化）">
          <span>加权分 <FilterOutlined style={{ fontSize: 11, color: '#faad14' }} /></span>
        </Tooltip>
      ),
      dataIndex: 'custom_score',
      width: 96,
      align: 'right',
      sorter: (a, b) => (a.custom_score || -1) - (b.custom_score || -1),
      render: (v, r) => (
        <span
          style={{
            color: scoreColor(v),
            fontWeight: v === null ? 400 : 600,
            fontVariantNumeric: 'tabular-nums',
          }}
          title={v === null ? '' : `等级：${r.custom_level}`}
        >
          {v === null ? '--' : v}
        </span>
      ),
    })
  }

  columns.push(
    {
      title: '等级',
      dataIndex: 'level',
      width: 92,
      render: (v, r) =>
        dimCustomized ? (
          <Tooltip title={`按加权分口径：${r.custom_level}`}>
            <Tag color={LEVEL_COLOR[v] || 'default'}>{v}</Tag>
          </Tooltip>
        ) : (
          <Tag color={LEVEL_COLOR[v] || 'default'}>{v}</Tag>
        ),
    },
    {
      title: 'AI',
      dataIndex: 'has_ai_summary',
      width: 56,
      align: 'center',
      render: (v) => (v ? <Tag color="blue">有</Tag> : <span style={{ color: '#666' }}>-</span>),
    },
    {
      title: '操作',
      width: 146,
      fixed: 'right',
      render: (_, r) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/candidates/${r.candidate_id}`)}
          >
            详情
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={() => navigate(`/interview/${r.candidate_id}`)}
          >
            面试
          </Button>
        </Space>
      ),
    }
  )

  // ---------- 展开明细：各维度平均分 + 各面试官平均分 ----------
  const expandedRowRender = (r) => {
    const da = r.dimension_avgs || {}
    const ia = r.interviewer_avgs || {}
    return (
      <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', padding: '4px 8px' }}>
        <div style={{ minWidth: 320, flex: 1 }}>
          <div style={{ fontSize: 12, color: '#a6a6a6', marginBottom: 8 }}>
            各维度平均分（跨 {r.rounds} 个已评分轮次）
          </div>
          {DIMENSIONS.map((d) => {
            const v = da[d.key]
            return (
              <div
                key={d.key}
                style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}
              >
                <span
                  style={{
                    width: 78,
                    fontSize: 12,
                    color: d.highlight ? '#faad14' : '#c0c0c0',
                    fontWeight: d.highlight ? 700 : 400,
                  }}
                >
                  {d.label}
                </span>
                <Progress
                  percent={v ?? 0}
                  showInfo={false}
                  size="small"
                  strokeColor={scoreColor(v)}
                  style={{ flex: 1, margin: 0 }}
                />
                <span
                  style={{
                    width: 74,
                    textAlign: 'right',
                    fontSize: 12,
                    fontVariantNumeric: 'tabular-nums',
                    color: v === undefined ? '#666' : '#e8e8e8',
                  }}
                >
                  {v === undefined ? '未评' : v}
                  {typeof dimPercent[d.key] === 'number' && (
                    <span style={{ color: '#666', marginLeft: 4 }}>
                      权重 {Math.round(dimPercent[d.key])}%
                    </span>
                  )}
                </span>
              </div>
            )
          })}
        </div>
        <div style={{ minWidth: 240 }}>
          <div style={{ fontSize: 12, color: '#a6a6a6', marginBottom: 8 }}>
            各面试官平均分（{Object.keys(ia).length} 人）
          </div>
          {Object.keys(ia).length === 0 ? (
            <span style={{ fontSize: 12, color: '#666' }}>暂无面试官打分</span>
          ) : (
            Object.entries(ia).map(([name, v]) => (
              <div
                key={name}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: 12,
                  marginBottom: 6,
                }}
              >
                <span>
                  <UserOutlined style={{ marginRight: 4, color: '#666' }} />
                  {name}
                  {typeof ivPercent[name] === 'number' && (
                    <span style={{ color: '#faad14', marginLeft: 6 }}>
                      权重 {Math.round(ivPercent[name])}%
                    </span>
                  )}
                </span>
                <span style={{ color: scoreColor(v), fontWeight: 600 }}>{v}</span>
              </div>
            ))
          )}
        </div>
      </div>
    )
  }

  if (loading && !data) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  // ---------- 权重弹窗内容 ----------
  const dimSum = Object.values(dimDraft).reduce((a, b) => a + (Number(b) || 0), 0)
  const ivValues = Object.values(ivDraft).map((v) => Number(v) || 0)
  const ivSum = ivValues.reduce((a, b) => a + b, 0)

  const dimPane = (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="四个维度的权重可以随便填（不必正好 100），系统会按比例自动归一化。"
      />
      {DIMENSIONS.map((d) => {
        const v = Number(dimDraft[d.key] ?? 0)
        const pct = dimSum > 0 ? ((v / dimSum) * 100).toFixed(1) : '0.0'
        return (
          <div key={d.key} style={{ marginBottom: 12 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 13,
                marginBottom: 4,
              }}
            >
              <span style={d.highlight ? { color: '#faad14', fontWeight: 700 } : undefined}>
                {d.label}
                {d.highlight && <Tag color="gold" style={{ marginLeft: 6 }}>放大显示</Tag>}
                <span style={{ color: '#666', marginLeft: 8, fontSize: 12, fontWeight: 400 }}>
                  默认 {Math.round(d.default * 100)}%
                </span>
              </span>
              <span style={{ color: '#a6a6a6', fontSize: 12 }}>实际占比 {pct}%</span>
            </div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <Slider
                min={0}
                max={100}
                value={v}
                onChange={(x) => setDimDraft((s) => ({ ...s, [d.key]: x }))}
                style={{ flex: 1, margin: 0 }}
              />
              <InputNumber
                min={0}
                max={100}
                value={v}
                onChange={(x) => setDimDraft((s) => ({ ...s, [d.key]: x ?? 0 }))}
                style={{ width: 86 }}
                addonAfter="%"
              />
            </div>
          </div>
        )
      })}
      <div style={{ fontSize: 12, color: '#a6a6a6' }}>合计 {dimSum}%（会自动归一化）</div>
    </div>
  )

  const ivPane = (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="面试官权重只影响「联评综合分」：默认每位面试官都是 1（等权）。想让组长/主面官的话更重，把它调高即可。"
      />
      {ivOptions.length === 0 ? (
        <Empty description="还没有面试官打分记录，先完成一次面试再来设定。" />
      ) : (
        ivOptions.map((name) => {
          const v = Number(ivDraft[name] ?? 1)
          const pct = ivSum > 0 ? ((v / ivSum) * 100).toFixed(1) : '0.0'
          return (
            <div
              key={name}
              style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}
            >
              <span style={{ flex: 1, fontSize: 13 }}>
                <UserOutlined style={{ marginRight: 6, color: '#666' }} />
                {name}
              </span>
              <InputNumber
                min={0}
                max={20}
                step={0.5}
                value={v}
                onChange={(x) => setIvDraft((s) => ({ ...s, [name]: x ?? 1 }))}
                style={{ width: 90 }}
              />
              <span
                style={{
                  width: 92,
                  textAlign: 'right',
                  fontSize: 12,
                  color: '#a6a6a6',
                }}
              >
                占比 {pct}%
              </span>
            </div>
          )
        })
      )}
      {ivOptions.length > 0 && (
        <div style={{ fontSize: 12, color: '#a6a6a6', marginTop: 8 }}>
          合计 {ivSum}（会自动归一化）
        </div>
      )}
    </div>
  )

  return (
    <div>
      {holder}
      <Row gutter={[14, 14]}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="候选人数" value={st.candidates ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="已评分人数"
              value={st.scored ?? 0}
              suffix={`/ ${st.candidates ?? 0}`}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="平均得分"
              value={st.average ?? '--'}
              prefix={<TrophyOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="联评平均（多面试官）"
              value={st.joint_average ?? '--'}
              suffix={
                st.multi_interviewer_candidates
                  ? `/ ${st.multi_interviewer_candidates} 人多人评`
                  : ''
              }
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="最高 / 最低"
              value={st.highest ?? '--'}
              suffix={` / ${st.lowest ?? '--'}`}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        {dimCustomized && (
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic
                title="加权平均（自定义权重）"
                value={st.custom_average ?? '--'}
                valueStyle={{ color: '#faad14' }}
              />
            </Card>
          </Col>
        )}
      </Row>

      <Card
        size="small"
        style={{ marginTop: 14 }}
        title="结果汇总（可按得分 / 维度 / 面试官排序）"
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
        }
      >
        {/* ---------------- 排序栏 ---------------- */}
        <div
          style={{
            display: 'flex',
            gap: 10,
            flexWrap: 'wrap',
            alignItems: 'center',
            marginBottom: 10,
          }}
        >
          <Segmented
            size="small"
            value={dimSort || ivSort ? undefined : segSort}
            onChange={onSegChange}
            options={sorts}
          />

          <Select
            size="small"
            allowClear
            className="sort-select-dim"
            placeholder="按维度排序"
            style={{ width: 148 }}
            value={dimSort || undefined}
            onChange={onDimChange}
            options={DIMENSIONS.map((d) => ({
              value: d.key,
              label: `${d.label}（${dimPercent[d.key] ?? Math.round(d.default * 100)}%）`,
            }))}
          />

          <Select
            size="small"
            allowClear
            className="sort-select-iv"
            placeholder="按面试官排序"
            style={{ width: 168 }}
            value={ivSort || undefined}
            onChange={onIvChange}
            disabled={ivOptions.length === 0}
            options={ivOptions.map((n) => ({ value: n, label: `${n} 的评分` }))}
          />

          <Button
            size="small"
            icon={<SettingOutlined />}
            type={dimCustomized || ivCustomized ? 'primary' : 'default'}
            ghost={dimCustomized || ivCustomized}
            onClick={() => setWeightsOpen(true)}
          >
            权重设置{(dimCustomized || ivCustomized) ? '（已修改）' : ''}
          </Button>

          <div style={{ flex: 1 }} />

          <Button
            size="small"
            icon={desc ? <ArrowDownOutlined /> : <ArrowUpOutlined />}
            onClick={() => setDesc((v) => !v)}
            disabled={sort === 'order' || sort === 'name'}
          >
            {desc ? '降序' : '升序'}
          </Button>
        </div>

        {/* 当前排序提示 */}
        {(dimSort || ivSort) && (
          <div style={{ marginBottom: 8, fontSize: 12 }}>
            <Tag color="gold">
              当前排序：{dimSort
                ? `按维度「${DIMENSIONS.find((d) => d.key === dimSort)?.label || dimSort}」`
                : `按面试官「${ivSort}」的平均分`}
              （{desc ? '从高到低' : '从低到高'}）
            </Tag>
          </div>
        )}

        <div style={{ marginBottom: 10, fontSize: 12, color: '#a6a6a6' }}>
          等级分布：
          {Object.entries(st.level_distribution || {}).map(([k, v]) => (
            <Tag key={k} color={LEVEL_COLOR[k] || 'default'} style={{ marginLeft: 6 }}>
              {k} {v}
            </Tag>
          ))}
          {(dimCustomized || ivCustomized) && (
            <span style={{ marginLeft: 10 }}>
              <TeamOutlined /> 权重已人工设定：
              {dimCustomized && <Tag color="gold" style={{ marginLeft: 6 }}>维度权重生效</Tag>}
              {ivCustomized && <Tag color="purple" style={{ marginLeft: 6 }}>面试官权重生效</Tag>}
            </span>
          )}
        </div>

        <Table
          size="small"
          rowKey="candidate_id"
          loading={loading}
          dataSource={data?.items || []}
          columns={columns}
          expandable={{ expandedRowRender, rowExpandable: () => true }}
          pagination={{ pageSize: 20, size: 'small', showSizeChanger: false }}
          scroll={{ x: dimCustomized ? 1420 : 1320 }}
          locale={{
            emptyText: <Empty description="暂无面试结果。完成至少一轮面试并保存后显示。" />,
          }}
        />
        <div style={{ fontSize: 12, color: '#666', marginTop: 8 }}>
          提示：点每一行左侧的展开箭头，可以看到该候选人在<b>各维度</b>上的平均分，以及
          <b>每位面试官</b>给出的平均分 —— 这些正是「按维度 / 按面试官排序」的依据。
        </div>
      </Card>

      {/* ---------------- 权重设置弹窗 ---------------- */}
      <Modal
        open={weightsOpen}
        onCancel={() => setWeightsOpen(false)}
        title={<span><SettingOutlined /> 给分权重设定（人工）</span>}
        width={640}
        okText="应用并保存"
        cancelText="取消"
        confirmLoading={savingWeights}
        onOk={applyWeights}
        footer={[
          <Button key="reset" danger onClick={resetWeights} loading={savingWeights}>
            恢复默认权重
          </Button>,
          <Button key="cancel" onClick={() => setWeightsOpen(false)}>
            取消
          </Button>,
          <Button key="ok" type="primary" onClick={applyWeights} loading={savingWeights}>
            应用并保存
          </Button>,
        ]}
      >
        <Tabs
          items={[
            { key: 'dim', label: '维度权重', children: dimPane },
            { key: 'iv', label: '面试官权重', children: ivPane },
          ]}
        />
        <Divider style={{ margin: '4px 0 10px' }} />
        <div style={{ fontSize: 12, color: '#a6a6a6', lineHeight: 1.7 }}>
          保存后所有端（电脑 / 手机）看到的汇总结果都会按新权重重算 ——
          权重属于评分规则，统一存在后端，避免各设备各调一套。
        </div>
      </Modal>
    </div>
  )
}
