import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Table, Input, Tag, Button, Space, Spin, Empty, message, Tooltip } from 'antd'
import { SearchOutlined, PlayCircleOutlined, EyeOutlined, ImportOutlined } from '@ant-design/icons'
import api from '../api'

const LEVEL_COLOR = {
  强烈推荐: 'red',
  推荐: 'orange',
  待定: 'blue',
  不推荐: 'default',
  未评分: 'default',
}

export default function CandidatesPage() {
  const navigate = useNavigate()
  const [msgApi, holder] = message.useMessage()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [onlyPending, setOnlyPending] = useState(false)
  const [importing, setImporting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.listCandidates({ q: q || undefined, only_pending: onlyPending })
      setRows(d.items || [])
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [q, onlyPending, msgApi])

  useEffect(() => {
    const t = setTimeout(load, 250) // 输入防抖
    return () => clearTimeout(t)
  }, [load])

  // 从面试顺序表（E:\InterviewSystem\Data\interview_order.xlsx）同步候选人名单
  const doImport = async () => {
    setImporting(true)
    try {
      const r = await api.importFromOrder()
      if (r.ok) {
        msgApi.success(r.message)
        if (r.added?.length) {
          msgApi.info(`新增候选人：${r.added.join('、')}`)
        }
      } else {
        msgApi.warning(r.message || '同步未成功，请检查顺序表文件。')
      }
      load()
    } catch (e) {
      msgApi.error(e.message)
    } finally {
      setImporting(false)
    }
  }

  const columns = [
    {
      title: '顺序',
      dataIndex: 'order_index',
      width: 66,
      sorter: (a, b) => (a.order_index || 0) - (b.order_index || 0),
      render: (v) => <span className="order-badge">{v ?? '-'}</span>,
    },
    {
      title: '姓名',
      dataIndex: 'name',
      width: 110,
      render: (v) => <span style={{ fontSize: 16, fontWeight: 700, color: '#fff' }}>{v}</span>,
    },
    {
      title: '学号',
      dataIndex: 'student_no',
      width: 116,
      render: (v) => (
        <span style={{ color: '#ffd666', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
          {v}
        </span>
      ),
    },
    { title: '专业', dataIndex: 'major', ellipsis: true },
    {
      title: '班级',
      dataIndex: 'grade',
      width: 150,
      render: (v) =>
        v ? (
          <Tag color="blue">{v}</Tag>
        ) : (
          <span style={{ color: '#666' }}>—</span>
        ),
    },
    { title: '应聘岗位', dataIndex: 'position', width: 110 },
    {
      title: '简历',
      dataIndex: 'resume_found',
      width: 74,
      render: (v) =>
        v ? <Tag color="green">有</Tag> : <Tag color="orange">无</Tag>,
    },
    {
      title: '已完成轮次',
      dataIndex: 'completed_rounds',
      width: 96,
      align: 'center',
      sorter: (a, b) => (a.completed_rounds || 0) - (b.completed_rounds || 0),
      render: (v) => (v ? <Tag color="blue">{v} 轮</Tag> : <span style={{ color: '#666' }}>0</span>),
    },
    {
      title: '最高得分',
      dataIndex: 'best_score',
      width: 92,
      align: 'right',
      sorter: (a, b) => (a.best_score || -1) - (b.best_score || -1),
      render: (v, r) =>
        v !== null && v !== undefined ? (
          <span style={{ color: '#ff4d4f', fontWeight: 600 }}>{v}</span>
        ) : (
          <span style={{ color: '#666' }}>--</span>
        ),
    },
    {
      title: '等级',
      dataIndex: 'level',
      width: 92,
      render: (v) => <Tag color={LEVEL_COLOR[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '操作',
      width: 150,
      fixed: 'right',
      render: (_, r) => (
        <Space size={4}>
          <Button
            size="small"
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={() => navigate(`/interview/${r.id}`)}
          >
            面试
          </Button>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/candidates/${r.id}`)}
          >
            详情
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Card
      size="small"
      title={`候选人列表（${rows.length} 人）`}
      extra={
        <Space>
          <Input
            allowClear
            size="small"
            prefix={<SearchOutlined />}
            placeholder="搜索姓名 / 学号 / 专业 / 岗位"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ width: 260 }}
          />
          <Button
            size="small"
            type={onlyPending ? 'primary' : 'default'}
            onClick={() => setOnlyPending((v) => !v)}
          >
            只看未面试
          </Button>
          <Tooltip title="读取 E:\InterviewSystem\Data\interview_order.xlsx，新增/更新候选人名单，并重新扫描 Resumes 目录挂简历。不会删除任何人。">
            <Button
              size="small"
              icon={<ImportOutlined />}
              loading={importing}
              onClick={doImport}
            >
              同步名单
            </Button>
          </Tooltip>
        </Space>
      }
    >
      {holder}
      <Table
        size="small"
        rowKey="id"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={{ pageSize: 20, size: 'small', showSizeChanger: false }}
        scroll={{ x: 1080 }}
        locale={{
          emptyText: (
            <Empty
              description={
                q
                  ? `没有匹配「${q}」的候选人`
                  : '暂无候选人：把名单 Excel 放到 E:\\InterviewSystem\\Data\\interview_order.xlsx 后点右上「同步名单」即可导入'
              }
            />
          ),
        }}
      />
    </Card>
  )
}
