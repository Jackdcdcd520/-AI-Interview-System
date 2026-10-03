import { useEffect, useState } from 'react'
import { Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom'
import { Tag, Tooltip, Badge } from 'antd'
import api from './api'

import HomePage from './pages/HomePage.jsx'
import InterviewPage from './pages/InterviewPage.jsx'
import CandidatesPage from './pages/CandidatesPage.jsx'
import ResultsPage from './pages/ResultsPage.jsx'
import CandidateDetailPage from './pages/CandidateDetailPage.jsx'

const NAV = [
  { to: '/', label: '首页', end: true },
  { to: '/interview', label: '面试' },
  { to: '/candidates', label: '候选人' },
  { to: '/results', label: '结果汇总' },
]

export default function App() {
  const [health, setHealth] = useState(null)
  const [healthError, setHealthError] = useState(null)
  const location = useLocation()

  useEffect(() => {
    let alive = true
    api
      .health()
      .then((d) => alive && setHealth(d))
      .catch((e) => alive && setHealthError(e.message))
    return () => {
      alive = false
    }
  }, [])

  const aiProvider = health?.ai?.active_provider
  const aiIsMock = aiProvider === 'mock'

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="app-logo">
          学生面试管理与智能评估系统
          <small>V1 · 本地运行</small>
        </div>

        <nav style={{ display: 'flex', gap: 4, flex: 1 }}>
          {NAV.map((n) => {
            const active = n.end
              ? location.pathname === n.to
              : location.pathname.startsWith(n.to)
            return (
              <NavLink
                key={n.to}
                to={n.to}
                style={{
                  padding: '6px 14px',
                  borderRadius: 6,
                  fontSize: 13.5,
                  textDecoration: 'none',
                  color: active ? '#fff' : '#a6a6a6',
                  background: active ? '#1668dc' : 'transparent',
                  transition: 'all .15s',
                }}
              >
                {n.label}
              </NavLink>
            )
          })}
        </nav>

        {healthError ? (
          <Tag color="error">后端未连接</Tag>
        ) : (
          <Tooltip
            title={
              aiIsMock
                ? '当前使用 mock provider（规则实现，无需 API Key）。在 config/settings.json 配置 deepseek 后可切换。'
                : `当前使用 ${aiProvider} provider`
            }
          >
            <Badge
              status={aiIsMock ? 'warning' : 'success'}
              text={
                <span style={{ fontSize: 12, color: '#a6a6a6' }}>
                  AI: {aiProvider || '...'}
                </span>
              }
            />
          </Tooltip>
        )}
      </header>

      <main className="app-content">
        {healthError && (
          <div
            className="panel"
            style={{ marginBottom: 16, borderColor: '#ff4d4f55' }}
          >
            <div className="panel-title" style={{ color: '#ff7875' }}>
              后端连接失败
            </div>
            <div className="empty-hint">
              {healthError}
              <br />
              启动命令：<span className="mono">scripts\start_all.bat</span>
            </div>
          </div>
        )}

        <Routes>
          <Route path="/" element={<HomePage health={health} />} />
          <Route path="/interview" element={<InterviewPage />} />
          <Route path="/interview/:candidateId" element={<InterviewPage />} />
          <Route path="/candidates" element={<CandidatesPage />} />
          <Route path="/candidates/:candidateId" element={<CandidateDetailPage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
