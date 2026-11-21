import React, { useEffect, useRef, useState } from 'react'

const API = '/api'
const STAGES = [
  { key: 'projects', ico: '🎬', lbl: '项目', enabled: true },
  { key: 'script', ico: '📝', lbl: '剧本', enabled: true },
  { key: 'assets', ico: '🎭', lbl: '资产', enabled: true },
  { key: 'storyboard', ico: '🎞️', lbl: '分镜', enabled: true },
  { key: 'voice', ico: '🎙️', lbl: '配音', enabled: true },
  { key: 'export', ico: '📤', lbl: '成片', enabled: true },
]
const ROLE_BY_ENTITY = { character: 'portrait', scene: 'scene', prop: 'prop' }
const ENTITY_LABEL = { character: '角色', scene: '场景', prop: '道具' }

async function api(path, opts) {
  const r = await fetch(API + path, opts)
  if (!r.ok) {
    const t = await r.text()
    throw new Error(t.slice(0, 300))
  }
  return r.json()
}
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const put = (path, body) => api(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const del = (path) => api(path, { method: 'DELETE' })
const patch = (path, body) => api(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const get = (path) => api(path)

function StageNav({ stage, setStage }) {
  return (
    <div className="stage-nav">
      {STAGES.map(s => (
        <div key={s.key}
          className={`stage-item ${stage === s.key ? 'active' : ''} ${s.enabled ? '' : 'disabled'}`}
          onClick={() => s.enabled && setStage(s.key)}>
          <span className="ico">{s.ico}</span><span className="lbl">{s.lbl}</span>
        </div>
      ))}
    </div>
  )
}

/* 阶段底部导航：上一步 / 下一步 */
function WizardBar({ stage, setStage, nextLabel }) {
  const idx = STAGES.findIndex(s => s.key === stage)
  const enabled = STAGES.filter(s => s.enabled)
  const prev = [...enabled].reverse().find(s => STAGES.indexOf(s) < idx)
  const next = enabled.find(s => STAGES.indexOf(s) > idx)
  return (
    <div className="wizard-bar">
      <button className="ghost" disabled={!prev} onClick={() => prev && setStage(prev.key)}>← 上一步</button>
      <button disabled={!next} onClick={() => next && setStage(next.key)}>{nextLabel || (next ? `下一步：${next.lbl} →` : '')}</button>
    </div>
  )
}

/* ---------- P0 项目中心 ---------- */
function ProjectsPage({ projects, reload, selectProject }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [confirmDel, setConfirmDel] = useState(null)  // 待确认删除的项目 {id,name}
  const [delMsg, setDelMsg] = useState('')
  const doDelete = async () => {
    if (!confirmDel) return
    try {
      await del(`/projects/${confirmDel.id}`)
      setDelMsg(`已删除项目「${confirmDel.name}」（含剧集、镜头与全部图片/视频产物）`)
      setConfirmDel(null)
      reload()
    } catch (e) {
      setDelMsg(`删除失败：${e.message}`)
    }
  }
  return (
    <div>
      <div className="page-title">项目中心</div>
      <div className="page-sub">项目 → 季 → 集，管理你的 AI 短剧作品</div>
      <div className="card">
        <label>新建项目</label>
        <div className="row">
          <input placeholder="项目名称" value={name} onChange={e => setName(e.target.value)} style={{ width: 260 }} />
          <input placeholder="一句话描述（可选）" value={desc} onChange={e => setDesc(e.target.value)} style={{ flex: 1 }} />
          <button disabled={!name.trim()} onClick={async () => { await post('/projects', { name, description: desc }); setName(''); setDesc(''); reload() }}>创建</button>
        </div>
      </div>
      <div className="grid">
        {projects.map(p => (
          <div key={p.id} className="asset-card" style={{ cursor: 'pointer' }} onClick={() => selectProject(p.id)}>
            <div className="info">
              <div className="name">{p.name}</div>
              <div className="desc">{p.description || '—'}</div>
              <div className="desc">创建于 {p.created_at.slice(0, 10)}</div>
              <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
                <button className="small ghost" onClick={e => { e.stopPropagation(); selectProject(p.id) }}>进入工作台 →</button>
                <button className="small ghost" title="删除项目及其全部数据"
                  onClick={e => { e.stopPropagation(); setDelMsg(''); setConfirmDel({ id: p.id, name: p.name }) }}>删除</button>
              </div>
            </div>
          </div>
        ))}
      </div>
      {confirmDel && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 99 }}
          onClick={() => setConfirmDel(null)}>
          <div className="card" style={{ minWidth: 340, maxWidth: 460 }} onClick={e => e.stopPropagation()}>
            <label style={{ color: '#c0392b' }}>确认删除项目</label>
            <div style={{ margin: '10px 0', fontSize: 13 }}>
              将永久删除「{confirmDel.name}」的全部数据：剧集、剧本、镜头、角色/场景/道具、暂存候选、任务记录，以及所有已生成的图片和视频文件。<b>该操作不可恢复。</b>
            </div>
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button className="ghost" onClick={() => setConfirmDel(null)}>取消</button>
              <button style={{ background: '#c0392b', borderColor: '#c0392b' }} onClick={doDelete}>永久删除</button>
            </div>
          </div>
        </div>
      )}
      {delMsg ? <div className="page-sub" style={{ marginTop: 8 }}>{delMsg}</div> : null}
      <WizardBar stage="projects" setStage={() => {}} />
    </div>
  )
}

/* ---------- P1 剧本工作台 ---------- */
/* ---------- 镜头卡（故事板数据层，决策 C） ---------- */
const CAMERA_MOVES = ['固定', '推', '拉', '横摇', '竖摇', '移', '跟', '升降', '环绕', '手持']
const CAMERA_SPEEDS = [['slow', '慢'], ['normal', '正常'], ['fast', '快'], ['whip', '甩镜']]

/* 批量生成操作条（M4/M5）：批量首帧 / 批量视频 / 一键全流程，幂等可重跑 */
function BatchBar({ episodeId, onDone }) {
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const go = async (kind, label, body = {}) => {
    setBusy(kind); setMsg(`${label}：任务已排队（GPU 串行执行，进度见底部任务栏）…`)
    try {
      const r = await post(`/episodes/${episodeId}/${kind}`, body)
      // 后台轮询：完成后刷新镜头状态
      const timer = setInterval(async () => {
        try {
          const ts = await api('/tasks?limit=3')
          const t = ts.find(x => String(x.id) === String(r.task_id))
          if (t && t.status === 'done') { clearInterval(timer); setBusy(''); setMsg(`${label} 完成，${t.stage || ''}`); onDone && onDone() }
          else if (t && t.status === 'failed') { clearInterval(timer); setBusy(''); setMsg(`${label} 失败：${(t.error || '').slice(0, 160)}`) }
          else setMsg(`${label} 进行中：${t?.stage || '排队'}…`)
        } catch { /* 网络抖动忽略 */ }
      }, 3000)
    } catch (e) { setBusy(''); setMsg(`${label} 提交失败：` + e.message) }
  }
  return (
    <div style={{ margin: '8px 0', padding: '8px 10px', border: '1px solid #3a4a5a', borderRadius: 8 }}>
      <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
        <button disabled={!!busy} onClick={() => go('batch-frames', '批量首帧')}>🖼 批量生成缺的首帧</button>
        <button disabled={!!busy} onClick={() => go('batch-videos', '批量视频')}>🎥 批量生成缺的视频</button>
        <button disabled={!!busy} style={{ borderColor: '#d0a030' }} onClick={() => go('full-pipeline', '一键全流程')}>⚡ 一键全流程（帧→视频→配音→成片）</button>
        <button disabled={!!busy} style={{ borderColor: '#d0a030' }} title="从第 1 镜开始逐镜用上镜视频末帧重绘下镜首帧再出视频，全链衔接+人物外观继承（覆盖所有镜的现有首帧和视频）"
          onClick={() => { if (confirm('⛓ 全链重刷：从第 1 镜起向后连锁重生成所有镜头（末帧接力），现有首帧和视频全部被覆盖，约 40-60 分钟。确定？')) go('rechain-from', '全链重刷', { from_idx: 1 }) }}>⛓ 全链重刷</button>
        <span className="page-sub" style={{ margin: 0 }}>已有产物的镜头自动跳过，可中断后重跑；重链类任务断链即停，修复后可从断点镜「向后重链」续跑</span>
      </div>
      {msg && <div className="page-sub" style={{ marginTop: 6 }}>{msg}</div>}
    </div>
  )
}

function StoryboardPage({ project, setStage, wizardStage = 'storyboard' }) {
  const [episodes, setEpisodes] = useState([])
  const [selId, setSelId] = useState(null)
  const [hasShots, setHasShots] = useState(false)
  useEffect(() => {
    (async () => {
      const list = await api(`/projects/${project.id}/episodes`)
      setEpisodes(list)
      if (list.length && !list.find(e => e.id === selId)) setSelId(list[0].id)
      else if (!list.length) setSelId(null)
    })()
  }, [project.id])
  useEffect(() => {
    (async () => {
      if (!selId) { setHasShots(false); return }
      try { setHasShots((await get(`/episodes/${selId}/shots`)).length > 0) } catch { setHasShots(false) }
    })()
  }, [selId])
  return (
    <div>
      <div className="page-title">分镜 · {project.name}</div>
      <div className="page-sub">镜头卡是视频生成的“运动说明书”：逐镜微调运镜/速度/人物轨迹，生成首帧、尾帧、宫格与单镜视频</div>
      {!episodes.length && <div className="page-sub">本项目还没有剧集，先去「剧本」页生成大纲与分集。</div>}
      {!!episodes.length &&
        <div className="row" style={{ alignItems: 'center' }}>
          <label style={{ margin: 0 }}>剧集</label>
          <select value={selId || ''} onChange={e => setSelId(Number(e.target.value))} style={{ maxWidth: 420 }}>
            {episodes.map(e => <option key={e.id} value={e.id}>第 {e.idx} 集 · {e.title || '（未命名）'}</option>)}
          </select>
        </div>}
      {selId && !hasShots &&
        <div className="page-sub">该集还没有镜头数据 —— 先去「剧本」页完成结构化拆解，再回到这里。</div>}
      {selId && hasShots && <BatchBar episodeId={selId} onDone={() => setHasShots(h => h)} />}
      {selId && <ShotsBoard key={selId} episodeId={selId} projectId={project.id} styleLock={project.style_preset} />}
      <WizardBar stage={wizardStage} setStage={setStage} />
    </div>
  )
}

/* ---------- 成片：配音（edge-tts）+ 逐镜拼接 + 字幕 ---------- */
function ExportPage({ project, setStage, wizardStage = 'export' }) {
  const [episodes, setEpisodes] = useState([])
  const [selId, setSelId] = useState(null)
  const [shots, setShots] = useState([])
  const [characters, setCharacters] = useState([])
  const [voiceMenu, setVoiceMenu] = useState([])
  const [status, setStatus] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState('')
  const [narrator, setNarrator] = useState('')

  useEffect(() => { api(`/projects/${project.id}/episodes`).then(l => { setEpisodes(l); if (l.length && !l.find(e => e.id === selId)) setSelId(l[0].id) }) }, [project.id])
  useEffect(() => { api(`/characters?project_id=${project.id}`).then(setCharacters).catch(() => {}) }, [project.id])
  useEffect(() => { api('/voice-presets').then(setVoiceMenu).catch(() => {}) }, [])
  useEffect(() => { api(`/projects/${project.id}/narrator-voice`).then(r => setNarrator(r.narrator_voice || '')).catch(() => {}) }, [project.id])

  const voiceGroups = Array.isArray(voiceMenu) ? voiceMenu : []
  const [voiceTaken, setVoiceTaken] = useState({})
  useEffect(() => { api(`/projects/${project.id}/voice-availability`).then(setVoiceTaken).catch(() => {}) }, [project.id, characters.length, narrator])
  const missingVoices = characters.filter(c => !c.voice)
  const voicesReady = !missingVoices.length && !!narrator
  const VoiceSelect = ({ value, onChange, genderHint }) =>
    <select value={value || ''} onChange={onChange} style={{ maxWidth: 240 }}>
      <option value="">— 未设置（必选）—</option>
      {voiceGroups.map(g => {
        // 性别匹配提示：角色性别能判断时，不符的组标注出来
        const gIsF = /女|f$/.test(g.group)
        const gIsM = /男|m$/.test(g.group)
        const mismatch = genderHint === 'f' ? gIsM : genderHint === 'm' ? gIsF : false
        return <optgroup key={g.group} label={g.group + (mismatch ? '（与角色性别不符）' : '')}>
        {g.items.map(v => {
          const owner = voiceTaken[v.voice]
          const mine = owner && (value === v.voice || (owner === '旁白' && narrator === v.voice))
          return <option key={v.key} value={v.voice} disabled={!!owner && !mine}>
            {v.label}{owner && !mine ? `（已被 ${owner} 使用）` : ''}</option>
        })}
        </optgroup>
      })}
    </select>
  const guessGender = c => {
    const d = `${c.description || ''}`.toLowerCase()
    const f = ['女','她','母','姐','妹','妻','婆','娘','妇','姨','female','woman','girl','lady']
    const m = ['男','他','父','叔','哥','弟','夫','爷','male','man','boy','guy']
    const isF = f.some(w => d.includes(w)), isM = m.some(w => d.includes(w))
    return isF && !isM ? 'f' : isM && !isF ? 'm' : null
  }

  const reload = async () => {
    if (!selId) return
    setShots(await get(`/episodes/${selId}/shots`).catch(() => []))
    get(`/episodes/${selId}/export-status`).then(setStatus).catch(() => setStatus(null))
  }
  useEffect(() => { reload() }, [selId])

  const waitTask = async (taskId) => {
    for (let i = 0; i < 300; i++) {
      await new Promise(r => setTimeout(r, 2000))
      try {
        const ts = await api('/tasks?limit=5')
        const t = ts.find(x => String(x.id) === String(taskId))
        if (t && t.status === 'done') return t
        if (t && t.status === 'failed') throw new Error(t.error || '任务失败')
      } catch (e) { if (e.message && e.message !== 'Failed to fetch') throw e }
    }
    throw new Error('等待超时')
  }

  const doTts = async () => {
    setBusy('tts'); setMsg('台词配音生成中（edge-tts 在线，每条秒级）…')
    try {
      const r = await post(`/episodes/${selId}/tts`, {})
      await waitTask(r.task_id)
      setMsg('配音完成。可继续合成成片。'); await reload()
    } catch (e) { setMsg('配音失败：' + e.message) }
    finally { setBusy('') }
  }
  const doExport = async () => {
    setBusy('export'); setMsg('成片合成中：拼接 → 混音 → 烧字幕（NVENC 硬编）…')
    try {
      const r = await post(`/episodes/${selId}/export-final`, {})
      await waitTask(r.task_id)
      setMsg('成片完成！'); await reload()
    } catch (e) { setMsg('合成失败：' + e.message) }
    finally { setBusy('') }
  }
  const saveVoice = async (cid, voice) => {
    await post(`/characters/${cid}/voice`, { voice })
    setCharacters(cs => cs.map(c => c.id === cid ? { ...c, voice } : c))
  }
  const saveNarrator = async (voice) => {
    await post(`/projects/${project.id}/narrator-voice`, { voice })
    setNarrator(voice)
  }
  const [previewing, setPreviewing] = useState('')
  const preview = (voice, tag) => {
    if (!voice) { setMsg('试听前先选择音色'); return }
    setPreviewing(tag)
    new Audio(`/api/voice-preview-file?voice=${encodeURIComponent(voice)}&pid=${project.id}&ts=${Date.now()}`)
      .play().catch(e => setMsg('试听播放失败（首次生成需几秒，再点一次）'))
    setTimeout(() => setPreviewing(''), 800)
  }
  const doExportDraft = async (kind, label) => {
    setBusy(kind); setMsg(`${label}导出中…`)
    try {
      const r = await post(`/episodes/${selId}/${kind}`, {})
      await waitTask(r.task_id)
      setMsg(`${label}导出完成`); await reload()
      const files = await get(`/episodes/${selId}/export-files`)
      setStatus(st => ({ ...st, ...files }))
    } catch (e) { setMsg(`${label}导出失败：` + e.message) }
    finally { setBusy('') }
  }

  const withVideo = shots.filter(s => s.video_path)
  const totalDur = shots.reduce((a, s) => a + (Number(s.duration) || 5), 0)
  const statusColor = s => s.video_path ? '#3a9d5c' : (s.first_frame_path ? '#d0a030' : '#a04040')
  return (
    <div>
      <div className="page-title">成片 · {project.name}</div>
      <div className="page-sub">逐镜视频无损拼接 → 台词配音混入（edge-tts 在线，零显存）→ SRT 字幕生成并烧录（NVENC 硬编）</div>
      {!!episodes.length &&
        <div className="row" style={{ alignItems: 'center' }}>
          <label style={{ margin: 0 }}>剧集</label>
          <select value={selId || ''} onChange={e => setSelId(Number(e.target.value))} style={{ maxWidth: 420 }}>
            {episodes.map(e => <option key={e.id} value={e.id}>第 {e.idx} 集 · {e.title || '（未命名）'}</option>)}
          </select>
        </div>}
      {!episodes.length && <div className="page-sub">本项目还没有剧集。</div>}

      {selId && !!shots.length &&
        <div style={{ margin: '12px 0' }}>
          <div className="page-sub">时间线粗剪（绿=有视频，黄=仅首帧，红=未制作；宽度≈时长，共 {totalDur}s）：</div>
          <div style={{ display: 'flex', height: 34, borderRadius: 6, overflow: 'hidden', gap: 1 }}>
            {shots.map(s =>
              <div key={s.id} title={`第 ${s.idx} 镜 · ${Number(s.duration) || 5}s · ${s.dialogue || '（无台词）'}`}
                   style={{ flexGrow: Number(s.duration) || 5, background: statusColor(s), opacity: .85,
                            color: '#fff', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {s.idx}
              </div>)}
          </div>
        </div>}

      <div style={{ margin: '10px 0' }}>
        <div className="page-sub">音色分配：试听 → 选择 → 自动保存锁死给该角色（未全部锁定前不能生成配音）：</div>
        <div className="row" style={{ alignItems: 'center', marginBottom: 4 }}>
          <label style={{ margin: 0, minWidth: 90 }}>旁白 / 无前缀台词</label>
          <VoiceSelect value={narrator} onChange={e => saveNarrator(e.target.value)} />
          <button className="ghost" style={{ marginLeft: 6 }} onClick={() => preview(narrator, 'narrator')}>{previewing === 'narrator' ? '…' : '🔊 试听'}</button>
        </div>
        {characters.map(c =>
          <div key={c.id} className="row" style={{ alignItems: 'center', marginBottom: 4 }}>
            <label style={{ margin: 0, minWidth: 90, color: c.voice ? '' : '#e0a030' }}>{c.name}{!c.voice && '（未锁定）'}</label>
            <VoiceSelect value={c.voice} genderHint={guessGender(c)} onChange={e => saveVoice(c.id, e.target.value)} />
            <button className="ghost" style={{ marginLeft: 6 }} onClick={() => preview(c.voice, c.id)}>{previewing === c.id ? '…' : '🔊 试听'}</button>
          </div>)}
      </div>

      {selId &&
        <div className="page-sub">
          本集镜头 {shots.length} 个，其中已出视频 {withVideo.length} 个、有台词 {shots.filter(s => s.dialogue).length} 个
          {shots.length > withVideo.length && <span style={{ color: '#e0a030' }}>　（{shots.length - withVideo.length} 个镜头未出视频，将跳过）</span>}
        </div>}
      <div className="row" style={{ margin: '10px 0', flexWrap: 'wrap', gap: 6 }}>
        <button disabled={!selId || busy || !shots.some(s => s.dialogue) || !voicesReady}
                title={voicesReady ? '' : '先把每个角色和旁白的音色试听并锁定'}
                onClick={doTts}>{busy === 'tts' ? '配音中…' : '🎙 生成台词配音'}</button>
        {!voicesReady && <span style={{ color: '#e0a030', fontSize: 12, alignSelf: 'center' }}>
          还有 {missingVoices.length} 个角色{!narrator && '、旁白'}未锁定音色</span>}
        <button disabled={!selId || busy || !withVideo.length} onClick={doExport}>{busy === 'export' ? '合成中…' : '🎬 合成成片'}</button>
        <button className="ghost" disabled={!selId || !!busy || !withVideo.length} onClick={() => doExportDraft('export-jianying', '剪映草稿')}>✂ 导出剪映草稿</button>
        <button className="ghost" disabled={!selId || !!busy || !withVideo.length} onClick={() => doExportDraft('export-fcpxml', 'FCPXML')}>🎞 导出 FCPXML</button>
      </div>
      {msg && <div className="page-sub">{msg}</div>}

      {(status?.jianying || status?.fcpxml) &&
        <div className="row" style={{ gap: 14, margin: '6px 0' }}>
          {status.jianying && <a href={status.jianying} download="draft_content.json">⬇ 剪映草稿 draft_content.json</a>}
          {status.fcpxml && <a href={status.fcpxml} download="timeline.fcpxml">⬇ FCPXML</a>}
        </div>}

      {status?.final_ready &&
        <div style={{ margin: '16px 0' }}>
          <div className="page-sub">成片预览：</div>
          <video controls src={status.final_file} style={{ maxWidth: 720, width: '100%' }} />
          <div className="row" style={{ marginTop: 6 }}>
            {status.srt_ready && <a href={status.srt_file} download="subtitle.srt">⬇ 下载 SRT 字幕</a>}
          </div>
        </div>}
      <WizardBar stage={wizardStage} setStage={setStage} nextLabel="" />
    </div>
  )
}

function ShotsBoard({ episodeId, projectId, styleLock }) {
  const [shots, setShots] = useState([])
  const [openId, setOpenId] = useState(null)
  const [genMsg, setGenMsg] = useState('')
  const [grids, setGrids] = useState({})     // shotId -> cells[]
  const [busy, setBusy] = useState({})       // shotId -> 'frame'|'end'|'video'|'grid'
  const [ipaW, setIpaW] = useState(0.70)     // IPAdapter 锁脸强度三档：0.55 / 0.70 / 0.85
  const [refsFor, setRefsFor] = useState(null)   // 正在看参考溯源的 shotId
  const [refsData, setRefsData] = useState(null)
  const isAnime = !styleLock || /anime|paint|国潮|动漫|水墨|美漫|日系|古风/.test(styleLock)

  const gen = async (id, kind, body) => {
    setBusy(b => ({ ...b, [id]: kind }))
    setGenMsg(`${kind} 任务已提交，可在任务面板看进度（8G 显存单镜视频约 3-6 分钟）`)
    try {
      const payload = { ...(body || {}) }
      if (kind === 'frame' || kind === 'grid') payload.ipa_weight = ipaW
      const r = await post(`/shots/${id}/${kind}`, payload)
      return r
    } catch (e) { setGenMsg('提交失败：' + e.message) }
    finally { setTimeout(() => setBusy(b => { const n = { ...b }; delete n[id]; return n }), 800) }
  }
  const genGrid = async (id) => {
    const r = await gen(id, 'grid')
    if (r) setGenMsg('宫格生成中，完成后点击「刷新」选格')
  }
  const chainNext = async (id) => {
    if (!confirm('镜头接力：用本镜末帧（尾帧或视频最后一帧）重绘出下一镜首帧，构图光影自然衔接？下一镜现有首帧会被覆盖。')) return
    try {
      const r = await post(`/shots/${id}/chain-next`, { strength: 0.35 })
      setGenMsg(`接力任务 #${r.task_id} 已入队（本镜 → 下一镜首帧，denoise 0.35 保留构图光影），完成后点「刷新」`)
    } catch (e) { setGenMsg('接力失败：' + e.message) }
  }
  const extendVideo = async (id) => {
    try {
      const r = await post(`/shots/${id}/extend-video`, { seconds: 3 })
      setGenMsg(`续写任务 #${r.task_id} 已入队（提视频末帧 → 续写 3 秒 → 无损拼接），完成后点「刷新」`)
    } catch (e) { setGenMsg('续写失败：' + e.message) }
  }
  const rechain = async (fromIdx) => {
    try {
      const r = await post(`/episodes/${episodeId}/rechain-from`, { from_idx: fromIdx })
      setGenMsg(`向后重链任务 #${r.task_id} 已入队（从第 ${fromIdx} 镜起：末帧→接力首帧→视频 连锁，断链即停），进度见底部任务栏`)
    } catch (e) { setGenMsg('重链失败：' + e.message) }
  }
  const genTalk = async (id, idx) => {
    if (!confirm(`🗣 第 ${idx} 镜说话镜头：用台词配音驱动口型/表情重新生成本镜视频（InfiniteTalk，口型跟音频，比普通 i2v 慢得多，约 10-20 分钟）。现有视频会被覆盖。确定？`)) return
    try {
      const r = await post(`/shots/${id}/talk`, {})
      setGenMsg(`说话镜头任务 #${r.task_id} 已入队（台词→逐句配音→InfiniteTalk 口型驱动），完成后点「刷新」`)
    } catch (e) { setGenMsg('说话镜头提交失败：' + e.message) }
  }
  const pickCell = async (id, cell_path) => {
    try { await post(`/shots/${id}/pick-grid-cell`, { cell_path }); load(); setGenMsg('已设为首帧') }
    catch (e) { setGenMsg('选格失败：' + e.message) }
  }
  // 参考溯源窗口：本镜生成实际用了哪些资产图 + 一键换
  const openRefs = async (id) => {
    setRefsFor(id)
    try { setRefsData(await get(`/shots/${id}/refs`)) } catch (e) { setRefsData(null); alert('取参考失败：' + e.message) }
  }
  const setRef = async (id, key, path) => {
    try { await patch(`/shots/${id}`, { ref_overrides: { [key]: path || '' } }) } catch (e) { alert('保存失败：' + e.message) }
    openRefs(id)
  }
  const refImg = (p, size, style) => p
    ? <img src={`/api/asset-file-by-path?path=${encodeURIComponent(p)}`} style={{ width: size, height: size * 1.25, objectFit: 'cover', borderRadius: 4, ...(style || {}) }} />
    : <div style={{ width: size, height: size * 1.25, border: '1px dashed #556', borderRadius: 4, fontSize: 10, color: 'var(--dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>无</div>

  const load = async () => {
    if (!episodeId) return
    try {
      const rows = await get(`/episodes/${episodeId}/shots`)
      setShots(rows)
      loadGrids(rows)
    } catch (e) { setShots([]) }
  }
  const loadGrids = async (rows) => {
    const g = {}
    await Promise.all((rows || []).map(async s => {
      try {
        const r = await get(`/shots/${s.id}/grid`)
        if (r && (r.cells || []).length) g[s.id] = r.cells
      } catch (e) { /* 无宫格忽略 */ }
    }))
    setGrids(g)
  }
  useEffect(() => { load() }, [episodeId])
  const onChange = async (id, body) => {
    try { await patch(`/shots/${id}`, body) } catch (e) { alert('保存失败：' + e.message) }
    load()
  }
  if (!shots.length) return null
  const endCount = shots.filter(s => s.needs_end_frame).length
  const statusBg = s => s.video_path ? '#2e7d4f' : (s.first_frame_path ? '#b8860b' : '#8a3a3a')
  const jumpTo = idx => document.getElementById(`shot-card-${idx}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return (
    <div className="cand-section">
      <h3>镜头时间轴（{shots.length} 镜 · 需出尾帧 {endCount} 镜）
        <button className="small ghost" style={{ marginLeft: 8 }}
          onClick={async () => { await post(`/episodes/${episodeId}/rebuild-prompts`, {}); load() }}>
          重组装全部提示词（不重跑 LLM）
        </button>
        <button className="small ghost" style={{ marginLeft: 6 }} onClick={load}>刷新</button>
      </h3>
      <div className="page-sub" style={{ fontSize: 12 }}>
        按时间轴顺序逐镜制作：每镜独立成卡——参考图（首帧/尾帧/场景锚点）、视频、生成操作都在本卡内，哪镜有问题单独重跑哪镜。
      </div>

      {/* mini 时间轴：点击色块跳转到对应镜头卡 */}
      <div style={{ display: 'flex', height: 26, borderRadius: 6, overflow: 'hidden', gap: 1, margin: '8px 0 14px' }}>
        {shots.map(s =>
          <div key={s.id} title={`第 ${s.idx} 镜 · ${Number(s.duration) || 5}s · ${s.dialogue || '（无台词）'}`}
            onClick={() => jumpTo(s.idx)}
            style={{ flexGrow: Number(s.duration) || 5, background: statusBg(s), opacity: .85, cursor: 'pointer',
                     color: '#fff', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {s.idx}
          </div>)}
      </div>

      {shots.map(s => (
        <div key={s.id} id={`shot-card-${s.idx}`}
          style={{ border: '1px solid #3a4a5a', borderRadius: 10, padding: '10px 12px', marginBottom: 14, background: 'rgba(255,255,255,0.02)' }}>
          {/* 卡片头 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ background: statusBg(s), color: '#fff', borderRadius: 6, padding: '2px 8px', fontSize: 13, fontWeight: 700 }}>#{s.idx}</span>
            <span style={{ fontSize: 12, color: 'var(--dim)' }}>{Number(s.duration) || 5}s · {s.shot_size}
              {s.framing_end && s.framing_end !== s.shot_size ? ` → ${s.framing_end}` : ''} · {s.camera_move || '固定'}/{s.camera_speed || 'normal'}</span>
            <span style={{ fontSize: 12 }}>{s.scene_name}</span>
            <span style={{ fontSize: 11, color: 'var(--dim)' }}>
              {(s.characters || []).length ? `角色：${(s.characters || []).join('、')}` : '空镜'}{(s.props || []).length ? ` · 道具：${(s.props || []).join('、')}` : ''}
            </span>
            <span style={{ fontSize: 11, color: 'var(--dim)', marginLeft: 'auto' }}>状态 {s.status || 'planned'}</span>
          </div>
          {s.dialogue ? <div style={{ fontSize: 12, margin: '4px 0 0', color: 'var(--dim)' }}>台词：{s.dialogue}{s.sfx ? `　音效：${s.sfx}` : ''}</div> : null}

          {/* 主体：参考图清单 | 视频 | 操作 */}
          <div style={{ display: 'flex', gap: 12, marginTop: 8, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--dim)' }}>首帧{s.first_frame_path ? '' : '（未生成）'}</div>
                {s.first_frame_path
                  ? <img src={`/api/shots/${s.id}/frame-file?which=first&t=${Date.now()}`}
                      style={{ width: 128, borderRadius: 6, border: '1px solid #556', cursor: 'pointer' }}
                      onClick={() => window.open(`/api/shots/${s.id}/frame-file?which=first`)} />
                  : <div style={{ width: 128, height: 72, borderRadius: 6, border: '1px dashed #556', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: 'var(--dim)' }}>待生成</div>}
              </div>
              {s.needs_end_frame &&
                <div>
                  <div style={{ fontSize: 11, color: 'var(--dim)' }}>尾帧{s.end_frame_path ? '' : '（未生成）'}</div>
                  {s.end_frame_path
                    ? <img src={`/api/shots/${s.id}/frame-file?which=end&t=${Date.now()}`}
                        style={{ width: 128, borderRadius: 6, border: '1px solid #556', cursor: 'pointer' }}
                        onClick={() => window.open(`/api/shots/${s.id}/frame-file?which=end`)} />
                    : <div style={{ width: 128, height: 72, borderRadius: 6, border: '1px dashed #556', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: 'var(--dim)' }}>待生成</div>}
                </div>}
              {s.scene_anchor_path &&
                <div>
                  <div style={{ fontSize: 11, color: '#d0a030' }}>场景锚⚓</div>
                  <img src={`/api/asset-file-by-path?path=${encodeURIComponent(s.scene_anchor_path)}`}
                    style={{ width: 84, height: 72, objectFit: 'cover', borderRadius: 6, border: '1px solid #d0a030', cursor: 'pointer' }}
                    onClick={() => window.open(`/api/asset-file-by-path?path=${encodeURIComponent(s.scene_anchor_path)}`)} />
                </div>}
              {grids[s.id] ? (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--dim)' }}>宫格候选</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 38px)', gap: 2 }}>
                    {grids[s.id].map((c, i) => (
                      <img key={i} src={`/api/shots/${s.id}/cell-file?i=${i}`}
                        onClick={() => pickCell(s.id, c)} title="设为首帧"
                        style={{ width: 38, display: 'block', borderRadius: 3, border: '1px solid #556', cursor: 'pointer' }} />
                    ))}
                  </div>
                </div>) : null}
            </div>

            <div>
              <div style={{ fontSize: 11, color: 'var(--dim)' }}>视频{s.video_path ? '' : '（未生成）'}</div>
              {s.video_path
                ? <video controls src={`/api/shots/${s.id}/video-file`} style={{ width: 200, borderRadius: 6, border: '1px solid #556' }} />
                : <div style={{ width: 200, height: 72, borderRadius: 6, border: '1px dashed #556', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: 'var(--dim)' }}>
                    {s.first_frame_path ? '有首帧，可生成视频' : '需先生成首帧'}</div>}
            </div>

            <div style={{ flex: 1, minWidth: 260 }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: 'var(--dim)' }} title="IPAdapter 锁脸强度">锁脸
                  <select value={ipaW} onChange={e => setIpaW(Number(e.target.value))} style={{ marginLeft: 3, fontSize: 11, padding: '1px 3px' }}>
                    <option value={0.55}>0.55</option><option value={0.70}>0.70</option><option value={0.85}>0.85</option>
                  </select>
                </span>
                <button className="small" disabled={!!busy[s.id]}
                  onClick={() => gen(s.id, 'frame', { frame_type: 'first' })}>
                  {busy[s.id] === 'frame' ? '提交中…' : '🖼 首帧'}
                </button>
                <button className="small ghost" onClick={() => openRefs(s.id)}
                  title="查看本镜生成实际引用的角色/场景资产图，可手动指定换用">🔍 参考{(s.ref_overrides && Object.keys(s.ref_overrides).length) ? ' ✓' : ''}</button>
                {s.needs_end_frame &&
                  <button className="small ghost" disabled={!!busy[s.id]}
                    onClick={() => gen(s.id, 'frame', { frame_type: 'end' })}>尾帧</button>}
                <button className="small" disabled={!!busy[s.id] || !s.first_frame_path}
                  title={s.first_frame_path ? '' : '需先生成首帧'}
                  onClick={() => gen(s.id, 'video', { duration: s.duration })}>
                  {busy[s.id] === 'video' ? '提交中…' : '🎥 视频'}
                </button>
                <button className="small ghost" disabled={!s.needs_end_frame && !s.video_path}
                  title="用本镜末帧重绘下一镜首帧，构图光影连贯"
                  onClick={() => chainNext(s.id)}>⏭ 接力</button>
                <button className="small ghost"
                  title={`从本镜起向后连锁重生成：本镜首帧以上一镜末帧重绘覆盖，逐镜 末帧→首帧→视频 向后传递（衔接+人物一致）。断链即停`}
                  onClick={() => { if (confirm(`⛓ 从第 ${s.idx} 镜向后重链：本镜及之后所有镜的首帧和视频将连锁重新生成（本镜以上一镜末帧为源），不可自动恢复。确定？`)) rechain(s.idx) }}>⛓ 向后重链</button>
                <button className="small ghost" disabled={!s.video_path}
                  title="视频不够长：提末帧续写 3s 再拼接"
                  onClick={() => extendVideo(s.id)}>⏩ 续写</button>
                <button className="small ghost" disabled={!!busy[s.id] || !s.first_frame_path || !(s.dialogue || '').trim()}
                  title={!(s.dialogue || '').trim() ? '需先在参数区填台词（角色名（语气）：台词）' : '台词配音驱动口型：重新生成本镜视频，口型/表情跟音频走'}
                  onClick={() => genTalk(s.id, s.idx)}>🗣 说话镜</button>
                {isAnime && <button className="small ghost" disabled={!!busy[s.id]}
                  onClick={() => genGrid(s.id)}>九宫格</button>}
              </div>
              <details style={{ marginTop: 8, fontSize: 12 }}>
                <summary style={{ cursor: 'pointer', color: 'var(--dim)' }}>参数与提示词（运镜/轨迹/3 条提示词）</summary>
                <div className="row" style={{ margin: '6px 0' }}>
                  <textarea value={s.dialogue || ''} placeholder={'台词，每行一句：小安（低语）：欢迎光临\n语气：平静/低语/紧张/急促/愤怒/悲伤/惊喜/温柔/迟疑/兴奋/冷峻\n旁白行不用名字前缀'}
                    onChange={e => setShots(rows => rows.map(r => r.id === s.id ? { ...r, dialogue: e.target.value } : r))}
                    onBlur={e => onChange(s.id, { dialogue: e.target.value })}
                    style={{ minHeight: 44, fontSize: 12, width: '100%' }} />
                </div>
                <div className="row" style={{ margin: '6px 0' }}>
                  <select value={s.camera_move} onChange={e => onChange(s.id, { camera_move: e.target.value })} style={{ width: 100, fontSize: 12 }}>
                    {CAMERA_MOVES.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <select value={s.camera_speed} onChange={e => onChange(s.id, { camera_speed: e.target.value })} style={{ width: 70, fontSize: 12, marginLeft: 4 }}>
                    {CAMERA_SPEEDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  <input value={s.character_path} placeholder="人物轨迹如 from left edge walks to counter"
                    onChange={e => setShots(rows => rows.map(r => r.id === s.id ? { ...r, character_path: e.target.value } : r))}
                    onBlur={e => onChange(s.id, { character_path: e.target.value })} style={{ flex: 1, fontSize: 12 }} />
                  <label style={{ fontSize: 11, marginLeft: 6 }}>
                    <input type="checkbox" checked={!!s.needs_end_frame}
                      onChange={e => onChange(s.id, { needs_end_frame: e.target.checked ? 1 : 0 })} /> 尾帧
                  </label>
                </div>
                <label style={{ fontSize: 11 }}>首帧提示词（{s.shot_size} · {s.camera_angle || '平视'}）</label>
                <textarea readOnly value={s.image_prompt} style={{ minHeight: 44, fontSize: 11, color: 'var(--dim)' }} />
                <label style={{ fontSize: 11 }}>视频运动提示词（喂 i2v · 三拍时间轴）</label>
                <textarea readOnly value={s.video_prompt} style={{ minHeight: 44, fontSize: 11, color: 'var(--dim)' }} />
                {s.needs_end_frame ? (<>
                  <label style={{ fontSize: 11 }}>尾帧提示词</label>
                  <textarea readOnly value={s.end_frame_prompt} style={{ minHeight: 44, fontSize: 11, color: 'var(--dim)' }} />
                </>) : null}
                {s.continuity_guidance ? <div className="page-sub" style={{ fontSize: 11 }}>轴线/承接：{s.continuity_guidance}</div> : null}
              </details>
            </div>
          </div>
        </div>
      ))}
      {genMsg ? <div className="page-sub">{genMsg}</div> : null}
      {/* 参考溯源窗口：本镜生成用了哪些资产图 + 手动换 */}
      {refsFor && refsData && (
        <div onClick={() => { setRefsFor(null); load() }}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ background: '#1c2836', border: '1px solid #3a4a5a', borderRadius: 10,
              padding: '14px 16px', maxWidth: 760, maxHeight: '82vh', overflowY: 'auto', width: '92%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <b>第 {refsData.idx} 镜 · 参考溯源</b>
              <span style={{ fontSize: 11, color: 'var(--dim)' }}>首帧生成时实际引用（点候选图即可换用，换后需重新生成首帧生效）</span>
              <button className="small ghost" style={{ marginLeft: 'auto' }}
                onClick={() => { setRefsFor(null); load() }}>关闭</button>
            </div>
            {refsData.characters.map(c => (
              <div key={c.name} style={{ marginTop: 12, borderTop: '1px solid #2a3a4a', paddingTop: 8 }}>
                <div style={{ fontSize: 12 }}>
                  <b>{c.name}</b>
                  <span style={{ marginLeft: 8, color: 'var(--dim)' }}>
                    当前：{c.used_path ? (c.source === 'manual' ? '手动指定' : `自动（${c.used_kind}）`) : '无可用人像参考'}
                  </span>
                  {c.source === 'manual' &&
                    <button className="small ghost" style={{ marginLeft: 8 }}
                      onClick={() => setRef(refsFor, c.name, '')}>清除指定</button>}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  <div title="当前使用">
                    {refImg(c.used_path, 64, { border: '2px solid #2a7' })}
                    <div style={{ fontSize: 10, color: '#2a7', textAlign: 'center' }}>使用中</div>
                  </div>
                  {c.candidates.filter(x => x.path !== c.used_path).map((x, i) => (
                    <div key={i} title={`点击换用（${x.kind}）`} style={{ cursor: 'pointer' }}
                      onClick={() => setRef(refsFor, c.name, x.path)}>
                      {refImg(x.path, 56, { border: '1px solid #556' })}
                      <div style={{ fontSize: 10, color: 'var(--dim)', textAlign: 'center' }}>{x.kind}</div>
                    </div>))}
                  {!c.candidates.length ? <span style={{ fontSize: 11, color: 'var(--dim)' }}>（角色资产库暂无单人参考图）</span> : null}
                </div>
              </div>))}
            <div style={{ marginTop: 12, borderTop: '1px solid #2a3a4a', paddingTop: 8 }}>
              <div style={{ fontSize: 12 }}>
                <b>场景锚⚓ {refsData.scene.name || '（未设置场景）'}</b>
                <span style={{ marginLeft: 8, color: 'var(--dim)' }}>
                  当前：{refsData.scene.used_path ? (refsData.scene.source === 'manual' ? '手动指定' : '自动（资产页选定锚点）') : '无锚图'}
                </span>
                {refsData.scene.source === 'manual' &&
                  <button className="small ghost" style={{ marginLeft: 8 }}
                    onClick={() => setRef(refsFor, '__scene__', '')}>清除指定</button>}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div title="当前使用">
                  {refImg(refsData.scene.used_path, 64, { border: '2px solid #d0a030' })}
                  <div style={{ fontSize: 10, color: '#d0a030', textAlign: 'center' }}>使用中</div>
                </div>
                {refsData.scene.candidates.filter(x => x.path !== refsData.scene.used_path).slice(0, 8).map((x, i) => (
                  <div key={i} title="点击换用为场景锚" style={{ cursor: 'pointer' }}
                    onClick={() => setRef(refsFor, '__scene__', x.path)}>
                    {refImg(x.path, 56, { border: '1px solid #556' })}
                  </div>))}
              </div>
            </div>
            {!!refsData.props.length && (
              <div style={{ marginTop: 12, fontSize: 12, borderTop: '1px solid #2a3a4a', paddingTop: 8 }}>
                <b>道具</b>
                <span style={{ marginLeft: 8, color: 'var(--dim)' }}>
                  {refsData.props.map(p => `${p.name}（${p.asset_count > 0 ? `资产库 ${p.asset_count} 张，仅提示词级引用` : '无定妆图，提示词级引用'}）`).join('、')}
                </span>
              </div>)}
          </div>
        </div>)}
    </div>
  )
}

/* ---------- 提示词模板（可编辑，M2.6） ---------- */
function PromptTemplatesPanel({ projectId }) {
  const [list, setList] = useState([])
  const [draft, setDraft] = useState({})
  const [open, setOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const load = async () => {
    try { setList(await get(`/prompt-templates?project_id=${projectId}`)) } catch (e) { setList([]) }
  }
  useEffect(() => { load() }, [projectId])
  const edit = (t) => setDraft(d => ({ ...d, [t.id]: t.content }))
  const copyAsCustom = async (t) => {
    try {
      await post('/prompt-templates', { project_id: projectId, stage: t.stage,
        name: t.name + '（我的版本）', content: t.content })
      load(); setMsg('已复制为可编辑模板')
    } catch (e) { setMsg('复制失败：' + e.message) }
  }
  const save = async (t) => {
    try {
      await put(`/prompt-templates/${t.id}`, { content: draft[t.id] ?? t.content })
      setMsg('已保存，下次重拆/重生成即生效'); load()
    } catch (e) { setMsg('保存失败：' + e.message) }
  }
  const setDefault = async (t) => {
    try { await put(`/prompt-templates/${t.id}`, { is_default: 1 }); load() }
    catch (e) { setMsg('切换失败：' + e.message) }
  }
  if (!list.length) return null
  return (
    <div className="cand-section">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <h3 style={{ margin: 0 }}>提示词模板（代码只填变量，措辞可自己改）</h3>
        <button className="small ghost" onClick={() => setOpen(!open)}>{open ? '收起' : '展开编辑'}</button>
        {msg ? <span className="page-sub" style={{ fontSize: 11 }}>{msg}</span> : null}
      </div>
      {open && (<>
        <div className="page-sub" style={{ fontSize: 11 }}>
          模板用 Jinja2 语法，可用变量见每行下方提示；系统预置模板不可删除，可改内容或另建自定义。
        </div>
        {list.map(t => (
          <div key={t.id} style={{ marginTop: 10 }}>
            <div style={{ fontSize: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
              <b>{t.stage_label}</b>
              <span style={{ color: 'var(--dim)' }}>{t.name}</span>
              {t.is_default ? <span style={{ color: '#2a7' }}>当前默认</span>
                : <button className="small ghost" onClick={() => setDefault(t)}>设为默认</button>}
              {t.is_system ? <button className="small ghost" onClick={() => copyAsCustom(t)}>复制为自定义</button> : null}
            </div>
            <textarea value={draft[t.id] ?? t.content} onChange={e => edit(t)} readOnly={!!t.is_system}
              style={{ minHeight: 66, fontSize: 11, fontFamily: 'ui-monospace, monospace',
                opacity: t.is_system ? 0.75 : 1 }} />
            <div style={{ fontSize: 10, color: 'var(--dim)' }}>
              变量：{(t.variables || []).join(' · ') || '—'}
              {t.is_system ? <span>（系统预置只读）</span>
                : <button className="small ghost" style={{ marginLeft: 8 }} onClick={() => save(t)}>保存</button>}
            </div>
          </div>
        ))}
      </>)}
    </div>
  )
}

// 国家/地区形象预设（与后端 ETHNICITY_PRESETS 对齐：value=槽位值，label=显示）
const ETHNICITIES = [
  ['chinese', '中国人'], ['korean', '韩国人'], ['japanese', '日本人'],
  ['american', '美国人'], ['european', '欧洲人'], ['african', '非洲人'],
  ['indian', '印度人'], ['southeast asian', '东南亚人'], ['middle eastern', '中东人'],
  ['latin', '拉丁裔'], ['russian', '俄罗斯人'],
]

function ScriptPage({ project, refreshTasks, setStage, setAssetsVersion }) {
  const [episodes, setEpisodes] = useState([])
  const [selId, setSelId] = useState(null)
  // 项目一句话描述自动带入大纲输入框（创建项目时填的 description）
  const [idea, setIdea] = useState(project.description || '')
  const [nEp, setNEp] = useState(3)
  // 分集列表分页：每页 5 集
  const [epPage, setEpPage] = useState(0)
  const [script, setScript] = useState('')
  const [breakdown, setBreakdown] = useState(null)
  const [checks, setChecks] = useState({})
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [presets, setPresets] = useState({})

  useEffect(() => { api('/style-presets').then(setPresets).catch(() => {}) }, [])

  const savePreset = async (key) => { await put(`/projects/${project.id}`, { style_preset: key }); project.style_preset = key }
  const currentPreset = project.style_preset || 'anime_2d'
  const [lifelike, setLifelike] = useState(project.lifelike !== 0)
  const [lifelikeFull, setLifelikeFull] = useState(project.lifelike_full === 1)
  const [autoPolish, setAutoPolish] = useState(project.auto_polish !== 0)
  const [gridBoard, setGridBoard] = useState(project.grid_storyboard !== 0)
  const [aspect, setAspect] = useState(project.aspect_ratio || '9:16')
  const toggleLifelike = async (v) => { setLifelike(v); await put(`/projects/${project.id}`, { lifelike: v ? 1 : 0 }) }
  const toggleLifelikeFull = async (v) => { setLifelikeFull(v); await put(`/projects/${project.id}`, { lifelike_full: v ? 1 : 0 }) }
  const toggleAutoPolish = async (v) => { setAutoPolish(v); await put(`/projects/${project.id}`, { auto_polish: v ? 1 : 0 }) }
  const toggleGrid = async (v) => { setGridBoard(v); await put(`/projects/${project.id}`, { grid_storyboard: v ? 1 : 0 }) }
  const ASPECTS = [
    { v: '9:16', label: '竖屏 9:16（默认）' },
    { v: '3:4', label: '竖屏 3:4' },
    { v: '1:1', label: '方形 1:1' },
    { v: '4:3', label: '横屏 4:3' },
    { v: '16:9', label: '横屏 16:9' },
    { v: '21:9', label: '横屏 21:9（超宽银幕）' },
  ]
  const setAspectRatio = async (v) => { setAspect(v); await put(`/projects/${project.id}`, { aspect_ratio: v }) }

  const loadEpisodes = async () => {
    const list = await api(`/projects/${project.id}/episodes`)
    setEpisodes(list)
    if (list.length && !list.find(e => e.id === selId)) setSelId(list[0].id)
    return list
  }
  useEffect(() => { loadEpisodes() }, [project.id])

  const sel = episodes.find(e => e.id === selId)
  useEffect(() => {
    setScript(sel ? sel.script_text : '')
    // 拆解结果持久化恢复：刷新页面/切集后依然能看到候选确认
    setBreakdown(null)
    if (selId) api(`/episodes/${selId}/breakdown`).then(bd => {
      if (bd.status === 'done') setBreakdown(bd.result)
    }).catch(() => {})
  }, [selId])

  const pollTask = async (after) => {
    for (let i = 0; i < 240; i++) {
      await new Promise(r => setTimeout(r, 2000))
      const ts = await api('/tasks?limit=1')
      refreshTasks()
      if (ts[0] && (ts[0].status === 'done' || ts[0].status === 'failed')) break
    }
    after && after()
  }

  const genOutline = async () => {
    setBusy(true)
    try { await post(`/projects/${project.id}/outline`, { idea, num_episodes: Number(nEp) }); await pollTask(loadEpisodes); setEpPage(0) }
    finally { setBusy(false) }
  }
  const continueOutline = async () => {
    setBusy(true)
    try {
      await post(`/projects/${project.id}/outline/continue`, { add_episodes: 10 })
      await pollTask(loadEpisodes)
      const list = await api(`/projects/${project.id}/episodes`)
      setEpisodes(list)
      setEpPage(Math.max(0, Math.floor((list.length - 1) / 5)))   // 跳到新分集所在末页
    } finally { setBusy(false) }
  }
  const saveScript = async () => { await put(`/episodes/${selId}`, { script_text: script }); loadEpisodes() }
  const writeScript = async () => {
    setBusy(true)
    try { await post(`/episodes/${selId}/write-script`); await pollTask(loadEpisodes); setScript((await api(`/projects/${project.id}/episodes`)).find(e => e.id === selId)?.script_text || '') }
    finally { setBusy(false) }
  }
  const doBreakdown = async () => {
    setBusy(true)
    try {
      await post(`/episodes/${selId}/breakdown`)
      for (let i = 0; i < 240; i++) {
        await new Promise(r => setTimeout(r, 2000))
        const bd = await api(`/episodes/${selId}/breakdown`)
        refreshTasks()
        if (bd.status === 'done') { setBreakdown(bd.result); break }
        if (bd.status === 'failed') { alert('拆解失败: ' + bd.error.slice(0, 200)); break }
      }
    } finally { setBusy(false) }
  }
  const reBreakdown = () => { setBreakdown(null); doBreakdown() }  // 回退重拆

  const toggle = (k) => setChecks(c => ({ ...c, [k]: !c[k] }))
  const [editing, setEditing] = useState({})
  const setSlot = (key, field, val, base) => setEditing(e => ({
    ...e, [key]: { ...(e[key] || base), [field]: val },
  }))
  const pickItems = (arr, prefix, kind) => (arr || [])
    .filter((_, i) => checks[`${prefix}${i}`] !== false)
    .map((c, i) => {
      const key = `${prefix}${arr.indexOf(c)}`
      const slots = editing[key] || { ...c, name: undefined, description: undefined, portrait_mode: undefined }
      return {
        name: c.name, description: c.description || '',
        slots, base_prompt: c.base_prompt || '',
        portrait_mode: kind === 'character' ? 'sheet' : 'sheet',   // 【硬性要求】角色一律三视图
      }
    })
  const confirmCandidates = async () => {
    if (!breakdown) return
    const cands = breakdown.candidates || {}
    setBusy(true)
    try {
      const r = await post(`/projects/${project.id}/confirm-candidates`, {
        characters: pickItems(cands.characters, 'c', 'character'),
        scenes: pickItems(cands.scenes, 's', 'scene'),
        props: pickItems(cands.props, 'p', 'prop'),
        generate_images: true,
      })
      setMsg(`已创建：角色 ${r.character_ids.length}、场景 ${r.scene_ids.length}、道具 ${r.prop_ids.length}；图片任务 ${r.task_ids.length} 个排队中。`
        + (r.skipped_dup?.length ? `（同名跳过：${r.skipped_dup.join('、')} —— 脸不变原则，服饰变化请在资产页用角色板重新渲染）` : ''))
      refreshTasks()
    } finally { setBusy(false) }
  }
  const stashCandidates = async () => {
    if (!breakdown) return
    const cands = breakdown.candidates || {}
    const items = [
      ...pickItems(cands.characters, 'c', 'character').map(x => ({ ...x, entity_type: 'character' })),
      ...pickItems(cands.scenes, 's', 'scene').map(x => ({ ...x, entity_type: 'scene' })),
      ...pickItems(cands.props, 'p', 'prop').map(x => ({ ...x, entity_type: 'prop' })),
    ]
    if (!items.length) { alert('没有勾选的候选'); return }
    setBusy(true)
    try {
      const r = await post(`/projects/${project.id}/stash`, { episode_id: selId, items })
      setMsg(`已暂存 ${r.stashed} 个候选到暂存区（资产页可查看；跨集复用时同名角色将保持脸部不变）。`)
    } finally { setBusy(false) }
  }

  const SLOT_FIELDS = {
    characters: [['identity', '身份'], ['ethnicity', '国家形象'], ['appearance', '身材五官'], ['hair', '发型发色'], ['clothing', '服装'], ['makeup', '妆造'], ['accessories', '饰品'], ['expression', '表情姿态'], ['chibi', 'Q版形象'], ['palette', '主色']],
    scenes: [['space', '空间结构'], ['era', '时代风格'], ['elements', '陈设元素'], ['light', '光线时段'], ['mood', '氛围']],
    props: [['category', '分类 core/bond'], ['subject', '本体'], ['purpose', '剧情功能'], ['era', '时代'], ['details', '细节'], ['material', '材质色彩'], ['interaction', '交互方式']],
  }
  const MODE_LABEL = { sheet: '三视图 16:9', single: '单人立绘竖版', board: '角色板（全要素）' }

  const slotsSummary = (c) => {
    const skip = ['name', 'description']
    return Object.entries(c).filter(([k, v]) => !skip.includes(k) && v).map(([k, v]) => `${k}: ${v}`).join(' | ')
  }

  const candTable = (k) => {
    const cands = ((breakdown && breakdown.candidates) || {})[k] || []
    const known = ((breakdown && breakdown.known_assets) || {})[k] || []
    return (
      <div className="cand-section" key={k}>
        <h3>
          {{ characters: '角色', scenes: '场景', props: '道具' }[k]}（新 {cands.length}
          {known.length ? ` · 资产库复用 ${known.length}` : ''}）
        </h3>
        {known.length ? <div className="page-sub" style={{ fontSize: 12 }}>已确认资产（镜头自动引用，无需重建）：{known.join('、')}</div> : null}
        <table className="cand-table">
          <tbody>
            {cands.map((c, i) => {
              const key = `${k[0]}${i}`
              const isOpen = !!editing[`open_${key}`]
              return (
                <React.Fragment key={i}>
                  <tr>
                    <td style={{ width: 40 }}><input type="checkbox" checked={checks[key] !== false} onChange={() => toggle(key)} /></td>
                    <td style={{ width: 110, fontWeight: 600 }}>{c.name}</td>
                    <td style={{ color: 'var(--dim)', width: 200 }}>{c.description}</td>
                    {k === 'characters' && (
                      <td style={{ width: 150 }}>
                        {/* 【硬性要求】角色资产必须三视图，版式选项已锁死 */}
                        <select value="sheet" disabled style={{ width: '100%' }} title="角色资产硬性要求：必须为三视图">
                          <option value="sheet">三视图 16:9（硬性要求）</option>
                        </select>
                      </td>
                    )}
                    <td style={{ color: 'var(--dim)', fontSize: 12 }}>{slotsSummary(c)}</td>
                    <td style={{ width: 90 }}>
                      <button className="small ghost" onClick={() => setEditing(e => ({ ...e, [`open_${key}`]: !isOpen }))}>
                        {isOpen ? '收起' : '✎ 槽位'}
                      </button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr><td colSpan={k === 'characters' ? 6 : 5} style={{ background: 'var(--bg2, #f6f7fb)' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 6, padding: 4 }}>
                        {SLOT_FIELDS[k].map(([f, lbl]) => (
                          <div key={f} className="row" style={{ alignItems: 'center' }}>
                            <span style={{ width: 86, color: 'var(--dim)', fontSize: 12, flexShrink: 0 }}>{lbl}</span>
                            {f === 'ethnicity' ? (
                              <select value={(editing[key] || c)[f] || ''} style={{ flex: 1, fontSize: 12 }}
                                onChange={e => setSlot(key, f, e.target.value, c)}>
                                <option value="">（未指定）</option>
                                {ETHNICITIES.map(([v, lbl2]) => <option key={v} value={v}>{lbl2}</option>)}
                              </select>
                            ) : (
                              <input value={(editing[key] || c)[f] || ''} placeholder={c[f] || ''}
                                onChange={e => setSlot(key, f, e.target.value, c)} style={{ flex: 1, fontSize: 12 }} />
                            )}
                          </div>
                        ))}
                      </div>
                    </td></tr>
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }

  const propNotes = (breakdown && breakdown.prop_notes) || {}
  const notesText = [
    propNotes.merged_ambient?.length ? `环境氛围道具（并入场景底板）：${propNotes.merged_ambient.join('、')}` : '',
    propNotes.skipped?.length ? `低频道具（出现<2次未晋升）：${propNotes.skipped.join('、')}` : '',
  ].filter(Boolean).join('　')

  const shotsTable = () => (
    <div className="cand-section">
      <h3>镜头拆解预览（{breakdown.shots?.length || 0} 镜 · M3 分镜阶段逐镜生成）</h3>
      <table className="cand-table">
        <thead><tr><th>#</th><th>场景</th><th>景别</th><th>运镜</th><th>秒</th><th>入镜角色</th><th>台词/音效</th><th>画面提示词</th></tr></thead>
        <tbody>
          {(breakdown.shots || []).map(s => (
            <tr key={s.idx}>
              <td>{s.idx}</td>
              <td style={{ fontSize: 12 }}>{s.scene_no} {s.scene_name}</td>
              <td>{s.shot_size}</td>
              <td>{s.camera}</td>
              <td>{s.duration}</td>
              <td style={{ fontSize: 12 }}>{(s.characters || []).join('、') || '—'}</td>
              <td style={{ fontSize: 12, color: 'var(--dim)' }}>{s.dialogue || s.sfx || '—'}</td>
              <td style={{ fontSize: 11, color: 'var(--dim)', maxWidth: 320 }}>{s.image_prompt}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ShotsBoard episodeId={selId} projectId={project?.id} styleLock={project?.style_preset} />
      {project && <PromptTemplatesPanel projectId={project.id} />}
    </div>
  )

  return (
    <div>
      <div className="page-title">剧本工作台 · {project.name}</div>
      <div className="page-sub">大纲 → 分集 → 剧本 → 结构化拆解 → 候选确认（每一步都可重跑、可手动编辑）</div>

      <div className="card">
        <label>全局风格锁（{Object.keys(presets).length} 种预设，注入所有剧本拆解与生图提示词，保证全片画风统一）</label>
        <div className="row">
          <select value={currentPreset} onChange={e => savePreset(e.target.value)} style={{ flex: 1 }}>
            {Object.entries(
              Object.entries(presets).reduce((acc, [k, v]) => {
                (acc[v.category] = acc[v.category] || []).push([k, v])
                return acc
              }, {})
            ).map(([cat, items]) => (
              <optgroup key={cat} label={`── ${cat} ──`}>
                {items.map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </optgroup>
            ))}
          </select>
          <span className="page-sub" style={{ fontSize: 12, flex: 2 }}>{presets[currentPreset]?.style_lock}</span>
        </div>
        <div className="page-sub" style={{ fontSize: 12, marginTop: 4 }}>视频动态策略：{presets[currentPreset]?.motion_hint}</div>
        <div className="row" style={{ marginTop: 8 }}>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={lifelike} onChange={e => toggleLifelike(e.target.checked)} />
            活人感机制（生活化瑕疵 + 真实光影 + 非模板姿态 + 规避过度渲染）
          </label>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer', marginLeft: 18 }}>
            <input type="checkbox" checked={lifelikeFull} onChange={e => toggleLifelikeFull(e.target.checked)} />
            全量瑕疵（连三视图/角色板也加五官不完美；只建议分镜用，会牺牲跨集一致性）
          </label>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer', marginLeft: 18 }}>
            <input type="checkbox" checked={autoPolish} onChange={e => toggleAutoPolish(e.target.checked)} />
            初图 10% 微调（分级：场景/道具/单人立绘 ON；三视图/角色板 OFF，可手动单张微调）
          </label>
          {(presets[currentPreset]?.category || '').includes('动漫') && (
            <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer', marginLeft: 18 }} title="九宫格候选构图→裁单格作首帧；写实风格易糊，建议关闭">
              <input type="checkbox" checked={gridBoard} onChange={e => toggleGrid(e.target.checked)} />
              宫格故事板（仅动漫风格建议开）
            </label>
          )}
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, marginLeft: 18 }} title="全局画幅：场景/道具/分镜首尾帧/宫格统一跟随；角色定妆照固定竖版不受影响。改动只对之后的新生成生效">
            全局画幅
            <select value={aspect} onChange={e => setAspectRatio(e.target.checked ? aspect : e.target.value)} style={{ fontSize: 13 }}>
              {ASPECTS.map(a => <option key={a.v} value={a.v}>{a.label}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="card">
        <label>① 一句话创意 / 大纲 → 生成分集</label>
        <div className="row">
          <input placeholder="例如：深夜便利店店员发现凌晨三点的神秘顾客…" value={idea} onChange={e => setIdea(e.target.value)} style={{ flex: 1 }} />
          <input type="number" min="1" max="60" value={nEp} onChange={e => setNEp(e.target.value)} style={{ width: 70 }} />
          <button disabled={busy || !idea.trim()} onClick={genOutline}>生成分集大纲</button>
        </div>
      </div>

      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div style={{ width: 320, flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <label style={{ marginBottom: 0 }}>② 分集列表</label>
            {!!episodes.length && (
              <button className="ghost" style={{ padding: '2px 10px', fontSize: 12 }} disabled={busy}
                onClick={continueOutline} title={`保留现有 ${episodes.length} 集，从第 ${episodes.length + 1} 集继续生成 10 集（含逐集 AI 剧本）`}>
                续写后 10 集 ›
              </button>
            )}
          </div>
          {(() => {
            const PER = 5
            const totalPages = Math.max(1, Math.ceil(episodes.length / PER))
            const cur = Math.min(epPage, totalPages - 1)
            if (cur !== epPage) setEpPage(cur)
            return <>
              {episodes.length > PER && (
                <div className="row" style={{ marginBottom: 8, alignItems: 'center' }}>
                  <button className="ghost" style={{ padding: '2px 8px' }} disabled={cur === 0} onClick={() => setEpPage(cur - 1)}>‹ 上一页</button>
                  <span style={{ fontSize: 12, opacity: .7, flex: 1, textAlign: 'center' }}>{cur + 1}/{totalPages} 页 · 共 {episodes.length} 集</span>
                  <button className="ghost" style={{ padding: '2px 8px' }} disabled={cur >= totalPages - 1} onClick={() => setEpPage(cur + 1)}>下一页 ›</button>
                </div>
              )}
              {episodes.slice(cur * PER, cur * PER + PER).map(e => (
                <div key={e.id} className={`episode-item ${e.id === selId ? 'selected' : ''}`} onClick={() => setSelId(e.id)}>
                  <div className="t">第 {e.idx} 集 · {e.title || '（未命名）'} <span className="badge">{e.status}</span></div>
                  <div className="s">{(e.outline || '').slice(0, 80)}…</div>
                </div>
              ))}
            </>
          })()}
          {!episodes.length && <div className="page-sub">暂无分集，先用上方创意生成。</div>}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {sel && <>
            <label>③ 本集剧本（可手写、AI 写、改完保存）</label>
            <textarea className="script-editor" value={script} onChange={e => setScript(e.target.value)} placeholder="剧本正文…" />
            <div className="row" style={{ marginTop: 8 }}>
              <button className="ghost" onClick={writeScript} disabled={busy}>AI 写本集剧本</button>
              <button onClick={saveScript} disabled={busy}>保存剧本</button>
              <button onClick={doBreakdown} disabled={busy || !script.trim()} style={{ background: 'var(--accent2)', color: '#fff' }}>④ 结构化拆解 →</button>
            </div>
          </>}
        </div>
      </div>

      {sel && sel.status === 'broken_down' && breakdown && (
        <div className="card" style={{ marginTop: 16 }}>
          <label>⑤ 拆解候选确认（勾选要创建的资产；确认后批量生成参考图，之后可在"资产"页逐个调整重渲染）</label>
          {['characters', 'scenes', 'props'].map(candTable)}
          {notesText && <div className="page-sub" style={{ fontSize: 12, margin: '4px 0' }}>{notesText}</div>}
          {shotsTable()}
          <div className="row">
            <button className="ghost small" onClick={reBreakdown} disabled={busy}>↺ 重新拆解（回退）</button>
            <button onClick={confirmCandidates} disabled={busy}>✔ 确认并批量生成参考图</button>
            <button className="ghost" onClick={stashCandidates} disabled={busy}>📥 暂存候选（跨集复用）</button>
            <button className="ghost" onClick={() => setStage('assets')}>前往资产页查看 →</button>
          </div>
        </div>
      )}
      {msg && <div className="card" style={{ borderColor: 'var(--ok)' }}>{msg}</div>}
      <WizardBar stage="script" setStage={setStage} nextLabel="下一步：查看资产 →" />
    </div>
  )
}

/* ---------- 资产编辑弹窗 ---------- */
function AssetEditor({ asset, models, onClose, refreshTasks, onDeleted }) {
  const role = ROLE_BY_ENTITY[asset._etype]
  const candidates = models.filter(m => m.role.includes(role))
  const [name, setName] = useState(asset.name)
  const [prompt, setPrompt] = useState(asset.base_prompt)
  const [slots, setSlots] = useState(asset.slots || {})
  const [genMode, setGenMode] = useState(asset.gen_mode || 'auto')
  const [modelKey, setModelKey] = useState('')
  const [tier, setTier] = useState('')
  const [versions, setVersions] = useState(asset.image_ids || [])
  const [delMsg, setDelMsg] = useState('')
  const defaultDims = () => (role === 'portrait'
    ? [1344, 768]   // 【硬性要求】角色必须三视图横幅，竖版通道已废弃
    : (role === 'scene' ? [1216, 704] : [832, 1216]))
  const [w, setW] = useState(defaultDims()[0])
  const [h, setH] = useState(defaultDims()[1])
  const [busy, setBusy] = useState(false)
  const img = id => `${API}/assets/${id}/file`

  const save = async () => {
    await put(`/entities/${asset._etype}/${asset.id}`,
      Object.keys(slots).length
        ? { name, slots, portrait_mode: role === 'portrait' ? 'sheet' : undefined, gen_mode: role === 'portrait' ? genMode : undefined }
        : { name, base_prompt: prompt, gen_mode: role === 'portrait' ? genMode : undefined })
    onClose(true)
  }
  const rerender = async () => {
    setBusy(true)
    try {
      if (Object.keys(slots).length) await put(`/entities/${asset._etype}/${asset.id}`, { name, slots, portrait_mode: role === 'portrait' ? 'sheet' : undefined, gen_mode: role === 'portrait' ? genMode : undefined })
      else await put(`/entities/${asset._etype}/${asset.id}`, { name, base_prompt: prompt, gen_mode: role === 'portrait' ? genMode : undefined })
      const r = await post('/regenerate', {
        project_id: asset.project_id, entity_type: asset._etype, entity_id: asset.id,
        model_key: modelKey || null, prefer_tier: tier || null, width: Number(w), height: Number(h),
      })
      refreshTasks()
      onClose(true, `重新渲染任务 #${r.task_id} 已入队，完成后回到这里查看新版本`)
    } finally { setBusy(false) }
  }
  const polish = async () => {
    if (!versions.length) { alert('该资产还没有图片，先渲染一张'); return }
    setBusy(true)
    try {
      const r = await post('/refine-image', { asset_id: versions[versions.length - 1], strength: 0.12 })
      refreshTasks()
      onClose(true, `10% 微调任务 #${r.task_id} 已入队（构图身份不变，仅补自然质感），完成后回来看新增版本`)
    } finally { setBusy(false) }
  }
  const rebuild = async () => {
    setBusy(true)
    try {
      const r = await post(`/entities/${asset._etype}/${asset.id}/rebuild-slots`)
      refreshTasks()
      onClose(true, `槽位重铸任务 #${r.task_id} 已入队：本地 LLM 会按方法论模板反推结构化槽位，完成后重新打开此资产即可逐槽微调`)
    } finally { setBusy(false) }
  }

  const redrawFromRef = async () => {
    if (asset._etype === 'character') { alert('角色一致性走 IPA 锁脸，不支持参考图重绘'); return }
    const url = prompt('粘贴真实参考图 URL（网上找的实物照片）。\n真实物品/场景用真实照片做底图重绘，结构、文字、比例保真，只换画风：')
    if (!url) return
    setBusy(true)
    try {
      const r = await post(`/entities/${asset._etype}/${asset.id}/from-reference`, { project_id: asset.project_id, image_url: url })
      refreshTasks()
      onClose(true, `参考图重绘任务 #${r.task_id} 已入队（denoise 0.5，结构文字保真）`)
    } finally { setBusy(false) }
  }
  const upscale = async () => {
    if (!versions.length) { alert('该资产还没有图片，先渲染一张'); return }
    setBusy(true)
    try {
      const r = await post('/upscale-image', { asset_id: versions[versions.length - 1] })
      refreshTasks()
      onClose(true, `超分放大任务 #${r.task_id} 已入队（像素级 2x/4x，构图身份不变，显存占用极小）`)
    } finally { setBusy(false) }
  }
  const deleteVersion = async (id) => {
    if (!confirm('删除这个历史版本？若它正被镜头首帧/尾帧/脸参考引用，引用会自动解除，防止后续进程错误调用。')) return
    setBusy(true)
    try {
      const r = await del(`/asset-images/${id}`)
      setVersions(versions.filter(x => x !== id))
      setDelMsg(`版本 #${id} 已删除${r.cleared?.shots ? `，已解除 ${r.cleared.shots} 处镜头引用` : ''}${r.cleared?.appearances ? `，已解除 ${r.cleared.appearances} 处脸参考引用` : ''}`)
      onDeleted && onDeleted()
    } finally { setBusy(false) }
  }
  const isScene = asset._etype === 'scene'
  const setAnchor = async (id) => {
    setBusy(true)
    try {
      await post(`/scenes/${asset.id}/set-anchor`, { asset_image_id: id })
      setDelMsg(`已设为场景锚点：该场景的所有镜头首帧将注入此图锁定环境一致性`)
      onDeleted && onDeleted()
    } catch (e) { setDelMsg('设置失败：' + e.message) }
    finally { setBusy(false) }
  }
  const clearAnchor = async () => {
    setBusy(true)
    try {
      await post(`/scenes/${asset.id}/clear-anchor`, {})
      setDelMsg('已清除场景锚点，镜头首帧回到纯提示词生成')
      onDeleted && onDeleted()
    } catch (e) { setDelMsg('清除失败：' + e.message) }
    finally { setBusy(false) }
  }
  const genIso = async () => {
    setBusy(true)
    try {
      const r = await post('/regenerate', {
        project_id: asset.project_id, entity_type: 'scene', entity_id: asset.id,
        iso_layout: true, width: 1216, height: 704,
      })
      refreshTasks()
      onClose(true, `空间布局图任务 #${r.task_id} 已入队（45° 等距俯瞰整个场景的结构与陈设），完成后在历史版本里点击 ⚓ 设为场景锚点`)
    } finally { setBusy(false) }
  }

  return (
    <div className="modal-mask" onClick={() => onClose(false)}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="page-title">{ENTITY_LABEL[asset._etype]}资产调整 · {asset.name}</div>
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div style={{ width: 300 }}>
            <label>历史版本（点击放大；✕ 删除；{isScene && '⚓ 设为场景锚点（环境一致性）'}）</label>
            <div className="row">
              {versions.map(id => (
                <span key={id} style={{ position: 'relative', display: 'inline-block' }}>
                  <img src={img(id)} style={{ width: 96, borderRadius: 8, cursor: 'pointer',
                       outline: asset.anchor_image_id === id ? '2px solid #d0a030' : 'none' }}
                    onClick={() => window.open(img(id))} />
                  <button className="small" title="删除此版本"
                    style={{ position: 'absolute', top: -8, right: -8, padding: '0 6px', background: '#c0392b', borderColor: '#c0392b', color: '#fff', borderRadius: 999 }}
                    disabled={busy} onClick={() => deleteVersion(id)}>✕</button>
                  {isScene &&
                    <button className="small" title={asset.anchor_image_id === id ? '当前锚点' : '设为场景锚点'}
                      style={{ position: 'absolute', bottom: -8, left: -8, padding: '0 5px',
                               background: asset.anchor_image_id === id ? '#d0a030' : '#2a3a4a', borderRadius: 999 }}
                      disabled={busy} onClick={() => asset.anchor_image_id === id ? clearAnchor() : setAnchor(id)}>⚓</button>}
                </span>
              ))}
              {!versions.length && <span className="page-sub">未生成</span>}
            </div>
            {isScene && asset.anchor_path &&
              <div style={{ color: '#d0a030', fontSize: 12, marginTop: 4 }}>⚓ 锚点已锁定：该场景镜头首帧自动注入此图（金框标记）</div>}
            {delMsg && <div style={{ color: 'var(--dim)', fontSize: 12, marginTop: 4 }}>{delMsg}</div>}
          </div>
          <div style={{ flex: 1 }}>
            <label>名称</label>
            <input value={name} onChange={e => setName(e.target.value)} />
            {Object.keys(slots).length ? (
              <>
                <label>结构化提示词槽位（改后自动按公式重组提示词，风格锁保持不变）</label>
                {role === 'portrait' && (
                  <>
                    <label>角色生成方式（三视图怎么出）</label>
                    <div className="row" style={{ marginBottom: 6 }}>
                      <select value={genMode} onChange={e => {
                        const gm = e.target.value
                        setGenMode(gm)
                        if (gm === 'sheet' || gm === 'layout' || gm === 'compose') { setW(1344); setH(768) }
                      }} style={{ flex: 1 }}>
                        <option value="auto">自动（按风格族推荐）</option>
                        <option value="compose">A · 程序合成三视图（正/侧/背分3次出图+PIL拼版，同seed）｜ 8G 显存足够，耗时约 3 倍</option>
                        <option value="layout">C · 版式模型整张多视图（Qwen-Image/Flux2）｜ 10G 以上推荐，8G 可跑但慢 3–5 倍</option>
                        <option value="sheet">单张多视图（低档底模直接出，动漫/国潮最稳）｜ 4–6G</option>
                      </select>
                    </div>
                    <div className="row" style={{ marginBottom: 6 }}>
                      <span style={{ color: 'var(--dim)', fontSize: 13 }}>构图模式：</span>
                      <select value="sheet" disabled style={{ flex: 1 }} title="角色资产硬性要求：必须为三视图版式">
                        <option value="sheet">三视图 16:9（硬性要求 · 不可更改）</option>
                      </select>
                    </div>
                  </>
                )}
                {Object.entries(slots).map(([k, v]) => (
                  <div className="row" key={k} style={{ marginBottom: 4 }}>
                    <span style={{ width: 90, color: 'var(--dim)', fontSize: 12, flexShrink: 0 }}>{k}</span>
                    {k === 'ethnicity' ? (
                      <select value={v || ''} onChange={e => setSlots(s => ({ ...s, [k]: e.target.value }))} style={{ flex: 1 }}>
                        <option value="">（未指定）</option>
                        {ETHNICITIES.map(([ev, el]) => <option key={ev} value={ev}>{el}</option>)}
                      </select>
                    ) : (
                      <input value={v || ''} onChange={e => setSlots(s => ({ ...s, [k]: e.target.value }))} style={{ flex: 1 }} />
                    )}
                  </div>
                ))}
                <label style={{ marginTop: 8 }}>最终提示词（自动组装，可直接查看）</label>
                <textarea value={prompt} readOnly style={{ minHeight: 70, color: 'var(--dim)' }} />
              </>
            ) : (
              <>
                <label>图像提示词（改完可保存或直接重新渲染）</label>
                <textarea value={prompt} onChange={e => setPrompt(e.target.value)} style={{ minHeight: 110 }} />
              </>
            )}
            <label>生成模型（不选则按显存自动选档）</label>
            <div className="row">
              <select value={modelKey} onChange={e => setModelKey(e.target.value)} style={{ flex: 1 }}>
                <option value="">自动（按显存选最优档）</option>
                {candidates.map(m => <option key={m.key} value={m.key}>{m.key} · {m.tier} · {m.vram_gb}GB</option>)}
              </select>
              <select value={tier} onChange={e => { setTier(e.target.value); if (e.target.value) setModelKey('') }}>
                <option value="">档位不限</option>
                <option value="low">低档（快）</option>
                <option value="mid">中档</option>
                <option value="high">高档</option>
              </select>
              <input type="number" value={w} onChange={e => setW(e.target.value)} style={{ width: 80 }} title="宽" />
              <span>×</span>
              <input type="number" value={h} onChange={e => setH(e.target.value)} style={{ width: 80 }} title="高" />
            </div>
            <div className="row" style={{ marginTop: 14 }}>
              <button className="ghost" onClick={save} disabled={busy}>保存修改</button>
              <button onClick={rerender} disabled={busy}>🔁 重新渲染</button>
              <button className="ghost" onClick={polish} disabled={busy} title="img2img denoise 0.12，构图与身份不变，仅补自然质感">✨ 微调10%</button>
              {asset._etype !== 'character' && <button className="ghost" onClick={redrawFromRef} disabled={busy} title="粘贴网上找的真实物品/场景照片，img2img 重绘：结构、比例、屏幕与键帽文字保真，只换画风">📷 参考图重绘</button>}
              {isScene && <button className="ghost" onClick={genIso} disabled={busy} title="生成 45° 等距空间布局全景图：俯瞰整个场景的结构与陈设排布，作为场景缩略图与锚点候选（镜头首帧 img2img 以此锁环境）">📐 布局图</button>}
              <button className="ghost" onClick={upscale} disabled={busy} title="像素级超分放大（写实 4xNomos / 动漫 4x-ESRGAN / 通用 RealESRGAN），构图身份不变，追加高清版本">🔍 超分放大</button>
              {!Object.keys(slots).length && <button className="ghost" onClick={rebuild} disabled={busy} title="本地 LLM 按方法论模板从描述反推结构化槽位">🪄 从描述重铸槽位</button>}
              <button className="ghost" onClick={() => onClose(false)}>关闭</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ---------- P2 资产库 ---------- */
function AssetsPage({ project, refreshTasks, setStage }) {
  const [data, setData] = useState(null)
  const [models, setModels] = useState([])
  const [editing, setEditing] = useState(null)
  const [notice, setNotice] = useState('')
  const [stash, setStash] = useState([])
  const [stashIds, setStashIds] = useState({})
  const [stashBusy, setStashBusy] = useState(false)

  const load = () => api(`/projects/${project.id}/assets`).then(setData)
  const loadStash = () => api(`/projects/${project.id}/stash`).then(setStash).catch(() => {})
  useEffect(() => { load() }, [project.id, project._assetsVersion])
  useEffect(() => { loadStash() }, [project.id])
  useEffect(() => { api('/system').then(s => setModels(Object.entries(s.models).map(([key, v]) => ({ key, ...v })))) }, [])
  if (!data) return <div className="page-sub">加载中…</div>
  const img = id => `${API}/assets/${id}/file`

  const stashConfirm = async (ids) => {
    if (!ids.length) return
    setStashBusy(true)
    try {
      const r = await post(`/projects/${project.id}/stash/confirm`, { ids, generate_images: true })
      setNotice(`暂存候选入库：角色 ${r.character_ids.length}、场景 ${r.scene_ids.length}、道具 ${r.prop_ids.length}。`
        + (r.skipped_dup?.length ? `（同名跳过：${r.skipped_dup.join('、')}）` : ''))
      loadStash(); load(); refreshTasks()
    } finally { setStashBusy(false) }
  }
  const stashDelete = async (id) => { await api(`/stash/${id}`, { method: 'DELETE' }); loadStash() }

  const stashCard = stash.length ? (
    <div className="card" style={{ borderColor: 'var(--accent2)', marginBottom: 14 }}>
      <label>候选暂存区（{stash.length}）—— 跨集资产复用：同名角色入库自动跳过（脸不变原则，服饰/妆造变化用角色板重渲染）</label>
      <table className="cand-table">
        <tbody>
          {stash.map(s => (
            <tr key={s.id}>
              <td style={{ width: 40 }}>
                <input type="checkbox" checked={stashIds[s.id] !== false}
                  onChange={() => setStashIds(x => ({ ...x, [s.id]: !(x[s.id] !== false) }))} />
              </td>
              <td style={{ width: 70 }}><span className="badge">{ENTITY_LABEL[s.entity_type]}</span></td>
              <td style={{ width: 120, fontWeight: 600 }}>{s.name}</td>
              <td style={{ color: 'var(--dim)', fontSize: 12 }}>{s.description}</td>
              <td style={{ color: 'var(--dim)', fontSize: 11 }}>
                {Object.entries(s.slots || {}).filter(([, v]) => v).slice(0, 3).map(([k, v]) => `${k}: ${String(v).slice(0, 30)}`).join(' | ')}
              </td>
              <td style={{ width: 60 }}>
                <button className="small ghost" onClick={() => stashDelete(s.id)}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row" style={{ marginTop: 6 }}>
        <button onClick={() => stashConfirm(stash.filter(s => stashIds[s.id] !== false).map(s => s.id))} disabled={stashBusy}>✔ 勾选入库并生成</button>
        <button className="ghost" onClick={() => stashConfirm(stash.map(s => s.id))} disabled={stashBusy}>全部入库</button>
      </div>
    </div>
  ) : null

  const deleteAsset = async (etype, a) => {
    if (!confirm(`删除资产「${a.name}」？将连同其全部生成图（${a.image_ids.length} 张）、角色造型变体一起删除，镜头引用自动解除。该操作不可恢复。`)) return
    try {
      const r = await del(`/entities/${etype}/${a.id}`)
      setNotice(`已删除${ENTITY_LABEL[etype]}「${a.name}」（清理 ${r.images_removed} 张图，解除 ${r.shots_cleared} 处镜头引用）`)
      load()
    } catch (e) { setNotice(`删除失败：${e.message}`) }
  }

  const wall = (list, etype, landscape) => (
    <>
      <h3 style={{ margin: '20px 0 10px', color: 'var(--accent)' }}>{ENTITY_LABEL[etype]}（{list.length}）<span className="page-sub" style={{ fontSize: 12 }}>点击卡片可编辑提示词 / 换模型 / 重新渲染</span></h3>
      <div className="grid">
        {list.map(a => (
          <div key={a.id} className={`asset-card ${landscape ? 'landscape' : ''}`} style={{ cursor: 'pointer', position: 'relative' }}
            onClick={() => setEditing({ ...a, _etype: etype, project_id: project.id })}>
            <button className="small" title="删除资产（含全部生成图，不可恢复）"
              style={{ position: 'absolute', top: 8, right: 8, zIndex: 2, background: '#c0392b', borderColor: '#c0392b', color: '#fff', opacity: 0.85 }}
              onClick={e => { e.stopPropagation(); deleteAsset(etype, a) }}>删除</button>
            {a.image_ids.length ? <img src={img(a.image_ids[a.image_ids.length - 1])} /> : <div style={{ aspectRatio: landscape ? '16/10' : '3/4', display: 'grid', placeItems: 'center', color: 'var(--dim)' }}>未生成 · 点击配置</div>}
            <div className="info">
              <div className="name">{a.name} {a.render_count > 0 && <span className="badge">渲染 {a.render_count} 次</span>}{a.image_ids.length > 1 && <span className="badge" title="含微调/超分等衍生图">{a.image_ids.length} 图</span>}</div>
              <div className="desc">{a.description}</div>
            </div>
          </div>
        ))}
      </div>
    </>
  )

  return (
    <div>
      <div className="page-title">资产库 · {project.name}</div>
      <div className="page-sub">每个资产都可以手动调整：改提示词、选模型档位、重新渲染追加新版本</div>
      {notice && <div className="card" style={{ borderColor: 'var(--ok)' }}>{notice}</div>}
      {stashCard}
      {wall(data.characters, 'character')}
      {wall(data.scenes, 'scene', true)}
      {wall(data.props, 'prop')}
      {editing && <AssetEditor asset={editing} models={models} refreshTasks={refreshTasks}
        onDeleted={load}
        onClose={(reload, note) => { setEditing(null); if (reload) load(); if (note) setNotice(note) }} />}
      <WizardBar stage="assets" setStage={setStage || (() => {})} nextLabel="下一步：分镜镜头卡 →" />
    </div>
  )
}

/* ---------- 底部任务栏 ---------- */
function TaskBar({ tasks, vram }) {
  const active = tasks.filter(t => t.status === 'running' || t.status === 'pending')
  const shown = active.length ? active : tasks.slice(0, 2)
  return (
    <div className="taskbar">
      <span className="vram">GPU 空闲 {vram?.vram_free_gb ?? '—'} / {vram?.vram_total_gb ?? '—'} GB</span>
      <span style={{ color: 'var(--dim)' }}>任务队列：</span>
      {shown.length ? shown.map(t => (
        <div key={t.id} className="task-item" title={t.stage || t.error}>
          <span className={`badge ${t.status}`}>{t.type}</span>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${Math.round((t.progress || 0) * 100)}%` }} /></div>
          <span>{t.stage || t.status}</span>
        </div>
      )) : <span style={{ color: 'var(--dim)' }}>空闲</span>}
    </div>
  )
}

export default function App() {
  // URL deep-link：?stage=script&project=1 直达任意页面（分享/演示/截图用）
  const _q = new URLSearchParams(location.search)
  const [stage, setStageRaw] = useState(_q.get('stage') || 'projects')
  const [projectId, setProjectId] = useState(Number(_q.get('project')) || null)
  const setStage = s => { setStageRaw(s); const u = new URL(location); u.searchParams.set('stage', s); history.replaceState(null, '', u) }
  const [projects, setProjects] = useState([])
  const [tasks, setTasks] = useState([])
  const [vram, setVram] = useState(null)
  const [assetsVersion, setAssetsVersion] = useState(0)

  const reloadProjects = () => api('/projects').then(setProjects)
  useEffect(() => { reloadProjects() }, [])

  useEffect(() => {
    const es = new EventSource(`${API}/tasks/stream`)
    es.onmessage = ev => {
      const { event, task } = JSON.parse(ev.data)
      if (event === 'task_update') {
        setTasks(old => {
          const i = old.findIndex(t => t.id === task.id)
          if (i >= 0) { const c = [...old]; c[i] = task; return c }
          return [task, ...old].slice(0, 30)
        })
        if (task.status === 'done' && ['asset', 'portrait'].includes(task.type)) setAssetsVersion(v => v + 1)
      }
    }
    return () => es.close()
  }, [])
  useEffect(() => {
    const tick = () => api('/system').then(s => setVram(s.comfyui)).catch(() => {})
    tick()
    const h = setInterval(tick, 5000)
    return () => clearInterval(h)
  }, [])

  const project = projects.find(p => p.id === projectId)
  const refreshTasks = () => api('/tasks?limit=10').then(setTasks)
  const needProject = stage !== 'projects' && !project

  return (
    <>
      <div className="layout">
        <StageNav stage={stage} setStage={setStage} />
        <div className="main">
          {needProject && <div className="page-sub">请先在"项目"页选择或创建项目。</div>}
          {stage === 'projects' && <ProjectsPage projects={projects} reload={reloadProjects} selectProject={id => { setProjectId(id); setStage('script') }} />}
          {stage === 'script' && project && <ScriptPage project={project} refreshTasks={refreshTasks} setStage={setStage} setAssetsVersion={setAssetsVersion} key={project.id} />}
          {stage === 'assets' && project && <AssetsPage project={{ ...project, _assetsVersion: assetsVersion }} refreshTasks={refreshTasks} setStage={setStage} />}
          {stage === 'storyboard' && project && <StoryboardPage project={project} setStage={setStage} />}
          {stage === 'voice' && project && <ExportPage project={project} setStage={setStage} wizardStage="voice" />}
          {stage === 'export' && project && <ExportPage project={project} setStage={setStage} />}
        </div>
      </div>
      <TaskBar tasks={tasks} vram={vram} />
    </>
  )
}
