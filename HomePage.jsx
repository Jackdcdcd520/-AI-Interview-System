import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Row, Col, Statistic, Button, Tag, List, Spin, Alert, Descriptions } from 'antd'
import {
  TeamOutlined, FileTextOutlined, CheckCircleOutlined, ClockCircleOutlined,
  PlayCircleOutlined, RobotOutlined, DatabaseOutlined, TrophyOutlined,
} from '@ant-design/icons'
import api from '../api'
import CandHighlight from '../components/CandHighlight'

export default function HomePage({ health }) {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)
  const [cur, setCur] = useState(null)

  useEffect(() => {
    api
      .statistics()
      .then(setStats)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false))
    api
      .current()
      .then(setCur)
      .catch(() => setCur(null))
  }, [])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  const cfg = health?.config || {}
  const ai = health?.ai || {}

  return (
    <div>
      {/* 当前/下一位候选人 —— 着重显示姓名学号班级 */}
      {cur?.candidate?.id && (
        <Card
          size="small"
          style={{ marginBottom: 14 }}
          title="下一位候选人（当前面试进度）"
          extra={
            <Button
              type="primary"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => navigate(`/interview/${cur.candidate.id}`)}
            >
              去面试
            </Button>
          }
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <span className="order-badge">{cur.position} / {cur.total}</span>
            <CandHighlight
              name={cur.candidate.name}
              studentNo={cur.candidate.student_no}
              grade={cur.candidate.grade}
            />
          </div>
        </Card>
      )}
      <Row gutter={[14, 14]}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="候选人总数"
              value={stats?.candidates ?? 0}
              prefix={<TeamOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="已完成面试"
              value={stats?.candidates_interviewed ?? 0}
              suffix={`/ ${stats?.candidates ?? 0}`}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="待面试"
              value={stats?.candidates_pending ?? 0}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="最高得分"
              value={stats?.highest_score ?? '--'}
              prefix={<TrophyOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[14, 14]} style={{ marginTop: 14 }}>
        <Col xs={24} lg={14}>
          <Card
            size="small"
            title="快速开始"
            extra={
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={() => navigate('/interview')}
              >
                进入面试
              </Button>
            }
          >
            <div className="empty-hint" style={{ marginBottom: 12 }}>
              面试流程：进入面试页 → 查看简历 → 打分 → 保存 → 下一位。
              当前指针会记住你面到第几位，刷新页面不会丢。
            </div>
            <Descriptions column={1} size="small" colon={false}
              styles={{ label: { color: '#a6a6a6', width: 100 } }}>
              <Descriptions.Item label="面试顺序">
                {stats?.interview_order?.exists ? (
                  <>
                    已读取 <strong>{stats.interview_order.rows}</strong> 条
                    <span className="mono" style={{ marginLeft: 8, color: '#666' }}>
                      {stats.interview_order.source}
                    </span>
                  </>
                ) : (
                  <span style={{ color: '#faad14' }}>
                    未找到面试顺序文件（系统仍可用，按数据库顺序面试）
                  </span>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="已完成轮次">
                {stats?.completed_rounds ?? 0} 轮
              </Descriptions.Item>
              <Descriptions.Item label="平均得分">
                {stats?.average_score ?? '--'}
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 12 }}>
              <Button onClick={() => navigate('/candidates')} style={{ marginRight: 8 }}>
                候选人列表
              </Button>
              <Button onClick={() => navigate('/results')}>结果汇总</Button>
            </div>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card size="small" title="运行环境">
            <Descriptions column={1} size="small" colon={false}
              styles={{ label: { color: '#a6a6a6', width: 92 }, content: { fontSize: 12.5 } }}>
              <Descriptions.Item label="后端">
                <span className="mono">{cfg.backend || '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="前端">
                <span className="mono">{cfg.frontend || '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="数据库">
                <span className="mono">{cfg.db_path || '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="简历目录">
                <span className="mono">{cfg.resume_dir || '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="版本">
                {cfg.version || '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card size="small" title={<><RobotOutlined /> AI 状态</>} style={{ marginTop: 14 }}>
            <div style={{ marginBottom: 8 }}>
              当前 Provider：{' '}
              <Tag color={ai.active_provider === 'mock' ? 'orange' : 'blue'}>
                {ai.active_provider || '-'}
              </Tag>
            </div>
            <List
              size="small"
              dataSource={ai.providers || []}
              renderItem={(p) => (
                <List.Item style={{ padding: '4px 0' }}>
                  <span style={{ fontSize: 13 }}>{p.name}</span>
                  {p.available ? (
                    <Tag color="green">可用</Tag>
                  ) : (
                    <Tag>不可用（缺 API Key）</Tag>
                  )}
                </List.Item>
              )}
            />
            <div className="ai-note">{ai.note}</div>
          </Card>
        </Col>
      </Row>

      {err && (
        <Alert
          style={{ marginTop: 14 }}
          type="error"
          showIcon
          message="读取统计失败"
          description={err}
        />
      )}

      {cfg.interview_order_exists === false && (
        <Alert
          style={{ marginTop: 14 }}
          type="warning"
          showIcon
          message="未检测到面试顺序文件"
          description={
            <>
              期望路径：<span className="mono">{cfg.interview_order_xlsx}</span>
              <br />
              可把你的 Excel 放到该位置，或运行
              <span className="mono"> scripts\make_test_data.py </span>
              生成测试数据后刷新。
            </>
          }
        />
      )}
    </div>
  )
}
