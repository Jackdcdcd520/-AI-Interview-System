/**
 * 姓名 / 学号 / 班级 着重显示（全站统一组件）。
 *
 *   <CandHighlight name="Demo" studentNo="2025000001" grade="示例班级2501" />
 *
 * 班级有值显示蓝色徽标，没有则显示灰色「班级：—」（留空占位，不遮挡排版）。
 * size="sm" 用于表格行等紧凑场景。
 */
export default function CandHighlight({ name, studentNo, grade, size }) {
  return (
    <span className={`cand-highlight${size === 'sm' ? ' sm' : ''}`}>
      <span className="cand-name">{name || '—'}</span>
      {studentNo && <span className="cand-no">{studentNo}</span>}
      {grade ? (
        <span className="cand-class">{grade}</span>
      ) : (
        <span className="cand-class empty">班级：—</span>
      )}
    </span>
  )
}
