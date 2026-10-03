import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card, Descriptions, Tag, Button, Space, Spin, Divider, Table,
  Progress, Empty, message, Alert, Tabs, Modal,
} from 'antd'
import {
  ArrowLeftOutlined, PlayCircleOutlined, RobotOutlined,
  ReloadOutlined, FileTextOutlined,
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

export default function CandidateDetailPage() {
  const { candidateId } = useParams()
  const navigate = useNavigate()
  const [msgApi, holder] = message.useMessage()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [resumeText, setResumeText] = useState(null)
  const [resumeModal, setResumeModal] = useState(false)
  const [parsing, setParsing] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.resultDetail(candidateId)
      setData(d)
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [candidateId, msgApi])

  useEffect(() => {
    load()
  }, [load])

  const showResume = async () => {
    try {
      const r = await api.getResume(candidateId)
      setResumeText(r)
      setResumeModal(true)
    } catch (e) {
      msgApi.error(e.message)
    }
  }

  const doParseResume = async () => {
    setParsing(true)
    try {
      const r = await api.extractResume(candidateId, true)
      if (!r.ok) {
        msgApi.warning(r.message || '未能解析简历')
      } else {
        msgApi.success(`简历解析完成（provider: ${r.provider || 'mock'}）`)
        await load()
      }
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setParsing(false)
    }
  }

  if (loading && !data) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  const c = data?.candidate || {}
  const parsed = data?.resume_parsed

  const ivColumns = [
    { title: '轮次', dataIndex: 'round', width: 64, render: (v) => <Tag color="blue">第 {v} 轮</Tag> },
    {
      title: '总分',
      dataIndex: 'total_score',
      width: 84,
      align: 'right',
      render: (v) => (
        <span style={{ color: v === null ? '#666' : '#ff4d4f', fontWeight: 600 }}>{v ?? '--'}</span>
      ),
    },
    {
      title: '等级',
      dataIndex: 'level',
      width: 92,
      render: (v) => <Tag color={LEVEL_COLOR[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 92,
      render: (v) =>
        v === 'completed' ? <Tag color="green">已完成</Tag> : <Tag color="gold">进行中</Tag>,
    },
    { title: '面试官', dataIndex: 'interviewer', width: 100, render: (v) => v || '-' },
    {
      title: '各维度得分',
      render: (_, r) => (
        <Space size={4} wrap>
          {(r.breakdown || [])
            .filter((d) => d.score !== null && d.score !== undefined)
            .map((d) => (
              <Tag key={d.key} style={{ fontSize: 11 }}>
                {d.label} {d.score}
              </Tag>
            ))}
        </Space>
      ),
    },
    { title: '评价', dataIndex: 'comment', ellipsis: true, render: (v) => v || '-' },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 152,
      render: (v) => <span style={{ fontSize: 12, color: '#a6a6a6' }}>{v || '-'}</span>,
    },
  ]

  return (
    <div>
      {holder}
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
          返回
        </Button>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          onClick={() => navigate(`/interview/${candidateId}`)}
        >
          进入面试
        </Button>
      </Space>

      <div className="interview-grid" style={{ gridTemplateColumns: 'minmax(320px,1fr) minmax(400px,1.6fr)' }}>
        {/* 左：基本信息 */}
        <div className="panel">
          <div className="panel-title">
            <CandHighlight
              size="sm"
              name={c.name}
              studentNo={c.student_no}
              grade={c.grade}
            />
            <Tag color={LEVEL_COLOR[data?.level] || 'default'}>{data?.level}</Tag>
          </div>

          {data?.best_score !== null && data?.best_score !== undefined && (
            <div style={{ margin: '6px 0 10px' }}>
              <span className="score-total high">{data.best_score}</span>
              <span style={{ color: '#a6a6a6', fontSize: 13, marginLeft: 8 }}>
                / 100 最高得分
              </span>
              <Progress
                percent={Math.min(100, data.best_score)}
                strokeColor="#ff4d4f"
                showInfo={false}
                style={{ marginTop: 6 }}
              />
            </div>
          )}

          {/* 联评综合评分（多面试官平均） */}
          {data?.joint?.has_data && (
            <div
              style={{
                background: '#101010',
                border: '1px solid #303030',
                borderRadius: 8,
                padding: '10px 12px',
                margin: '6px 0 12px',
              }}
            >
              <div style={{ fontSize: 12, color: '#a6a6a6', marginBottom: 4 }}>
                联评综合评分（{data.joint.interviewer_count} 位面试官平均）
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span
                  className={`score-total ${
                    data.joint.joint_score >= 75
                      ? 'high'
                      : data.joint.joint_score >= 60
                        ? 'mid'
                        : 'low'
                  }`}
                >
                  {data.joint.joint_score}
                </span>
                <Tag color={LEVEL_COLOR[data.joint.joint_level] || 'default'}>
                  {data.joint.joint_level}
                </Tag>
                <span style={{ fontSize: 12, color: '#666' }}>
                  {data.joint.consensus}
                  {data.joint.std !== null ? `（σ=${data.joint.std}）` : ''}
                </span>
              </div>
              <div style={{ marginTop: 8 }}>
                {data.joint.interviewers.map((iv) => (
                  <div
                    key={iv.interviewer}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 12,
                      padding: '2px 0',
                    }}
                  >
                    <span style={{ color: '#c0c0c0' }}>
                      {iv.interviewer}
                      <span style={{ color: '#666', marginLeft: 6 }}>{iv.rounds} 轮</span>
                    </span>
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {iv.avg_score}
                      <span style={{ color: '#666', marginLeft: 4 }}>
                        （{iv.scores.join(' / ')}）
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <Descriptions column={1} size="small" colon={false}
            styles={{ label: { color: '#a6a6a6', width: 76 }, content: { fontSize: 13 } }}>
            <Descriptions.Item label="学号">{c.student_no || '-'}</Descriptions.Item>
            <Descriptions.Item label="专业">{c.major || '-'}</Descriptions.Item>
            <Descriptions.Item label="班级">{c.grade || '-'}</Descriptions.Item>
            <Descriptions.Item label="应聘岗位">{c.position || '-'}</Descriptions.Item>
            <Descriptions.Item label="手机">{c.phone || '-'}</Descriptions.Item>
            <Descriptions.Item label="邮箱">{c.email || '-'}</Descriptions.Item>
            <Descriptions.Item label="面试顺序">第 {c.order_index || '-'} 位</Descriptions.Item>
            <Descriptions.Item label="已完成轮次">{data?.rounds ?? 0} 轮</Descriptions.Item>
            <Descriptions.Item label="简历文件">
              {c.resume_file || <span style={{ color: '#faad14' }}>无</span>}
            </Descriptions.Item>
          </Descriptions>

          <Divider style={{ margin: '12px 0' }} />

          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            {c.resume_exists && (
              <Button icon={<FileTextOutlined />} onClick={showResume} block>
                查看简历
              </Button>
            )}
            <Button
              icon={<RobotOutlined />}
              onClick={doParseResume}
              loading={parsing}
              block
              disabled={!c.resume_exists}
            >
              AI 解析简历
            </Button>
          </Space>

          {parsed && (
            <>
              <Divider style={{ margin: '12px 0 8px' }} />
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                简历结构化结果
                <Tag style={{ marginLeft: 6 }}>{parsed.extracted_by || '-'}</Tag>
              </div>
              <div className="resume-box" style={{ maxHeight: 260 }}>
                {JSON.stringify(parsed, null, 2)}
              </div>
            </>
          )}
        </div>

        {/* 右：全部面试记录 */}
        <div className="panel">
          <div className="panel-title">
            <span>面试记录（{data?.interviews?.length ?? 0} 条）</span>
            <Button size="small" icon={<ReloadOutlined />} onClick={load}>
              刷新
            </Button>
          </div>

          {!data?.interviews?.length ? (
            <Empty description="该候选人还没有面试记录" />
          ) : (
            <Tabs
              items={(data.interviews || []).map((iv) => ({
                key: String(iv.id),
                label: `第 ${iv.round} 轮${iv.total_score !== null && iv.total_score !== undefined ? ` · ${iv.total_score}` : ''}`,
                children: (
                  <div>
                    <Descriptions column={2} size="small" colon={false}
                      styles={{ label: { color: '#a6a6a6' }, content: { fontSize: 13 } }}>
                      <Descriptions.Item label="总分">
                        <span style={{ color: '#ff4d4f', fontWeight: 600 }}>
                          {iv.total_score ?? '--'}
                        </span>
                      </Descriptions.Item>
                      <Descriptions.Item label="等级">
                        <Tag color={LEVEL_COLOR[iv.level] || 'default'}>{iv.level}</Tag>
                      </Descriptions.Item>
                      <Descriptions.Item label="面试官">{iv.interviewer || '-'}</Descriptions.Item>
                      <Descriptions.Item label="状态">
                        {iv.status === 'completed' ? '已完成' : '进行中'}
                      </Descriptions.Item>
                      <Descriptions.Item label="AI Provider">
                        {iv.ai_provider || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="更新时间">{iv.updated_at || '-'}</Descriptions.Item>
                    </Descriptions>

                    <Divider style={{ margin: '10px 0' }} />
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>维度得分</div>
                    {(iv.breakdown || []).map((d) => (
                      <div className="dim-row" key={d.key}>
                        <span className="dim-label">
                          {d.label}
                          <span className="weight-tag">{Math.round((d.weight || 0) * 100)}%</span>
                        </span>
                        <Progress
                          percent={d.score ?? 0}
                          size="small"
                          showInfo={false}
                          strokeColor={d.score >= 75 ? '#ff4d4f' : '#1668dc'}
                        />
                        <span className="dim-score">{d.score ?? '-'}</span>
                      </div>
                    ))}

                    {iv.comment && (
                      <>
                        <Divider style={{ margin: '10px 0' }} />
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                          面试官评价
                        </div>
                        <div style={{ fontSize: 13, color: '#c0c0c0', lineHeight: 1.8 }}>
                          {iv.comment}
                        </div>
                      </>
                    )}

                    {iv.ai_summary && (
                      <>
                        <Divider style={{ margin: '10px 0' }} />
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                          AI 面试总结
                        </div>
                        <div
                          style={{
                            fontSize: 13,
                            lineHeight: 1.8,
                            background: '#101010',
                            border: '1px solid #303030',
                            borderRadius: 8,
                            padding: 10,
                          }}
                        >
                          {iv.ai_summary}
                        </div>
                      </>
                    )}

                    {iv.ai_evaluation && (
                      <>
                        <Divider style={{ margin: '10px 0' }} />
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                          AI 智能评估
                        </div>
                        <div style={{ fontSize: 13, color: '#c0c0c0', marginBottom: 6 }}>
                          {iv.ai_evaluation.summary}
                        </div>
                        {(iv.ai_evaluation.strengths || []).map((s, i) => (
                          <div key={i} style={{ paddingLeft: 10, color: '#ff7875', fontSize: 13 }}>
                            + {s}
                          </div>
                        ))}
                        {(iv.ai_evaluation.weaknesses || []).map((s, i) => (
                          <div key={i} style={{ paddingLeft: 10, color: '#95de64', fontSize: 13 }}>
                            - {s}
                          </div>
                        ))}
                        {iv.ai_evaluation.suggestion && (
                          <Alert
                            type="info"
                            showIcon
                            style={{ marginTop: 8, fontSize: 13 }}
                            message="建议"
                            description={iv.ai_evaluation.suggestion}
                          />
                        )}
                      </>
                    )}
                  </div>
                ),
              }))}
            />
          )}

          <Divider style={{ margin: '10px 0' }} />
          <Table
            size="small"
            rowKey="id"
            dataSource={data?.interviews || []}
            columns={ivColumns}
            pagination={false}
            locale={{ emptyText: '暂无记录' }}
          />
        </div>
      </div>

      <Modal
        open={resumeModal}
        title={`简历 — ${c.name}`}
        onCancel={() => setResumeModal(false)}
        footer={[
          c.resume_exists && (
            <Button
              key="raw"
              href={api.resumeFileUrl(candidateId)}
              target="_blank"
              rel="noreferrer"
            >
              打开原件
            </Button>
          ),
          <Button key="close" type="primary" onClick={() => setResumeModal(false)}>
            关闭
          </Button>,
        ]}
        width={800}
      >
        {resumeText?.resume?.found ? (
          <div className="resume-box" style={{ maxHeight: 520 }}>
            {resumeText.text || '（未抽取到文字）'}
          </div>
        ) : (
          <Empty description={resumeText?.resume?.message || '未找到简历'} />
        )}
      </Modal>
    </div>
  )
}
