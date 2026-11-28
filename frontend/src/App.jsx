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
const ENTITY_LABEL = { character: '角色', scene: '场景设计图', prop: '道具设计图' }
// 资产槽位中文释义（表单左侧灰字 → 右侧字段名，避免满屏英文键名）
const SLOT_ZH = {
  identity: '身份', ethnicity: '国籍/人种', build: '体型', appearance: '外貌气质',
  face: '面部特征', hair: '发型', clothing: '服装', accessories: '配饰',
  expression: '表情', pose: '姿态', palette: '配色', material: '材质',
  shape: '形状结构', text: '文字/标识', text_content: '牌面文字（要写的中文）', lighting: '光线氛围', layout: '空间布局',
}

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

/* 视频档（用户自选）：分镜页下拉选择，单镜/批量/重链全部按此档出视频。
   存 localStorage，选中后跨页保持；'' = 用后端默认档（models.yaml defaults）。 */
const VIDEO_KEY_LS = 'ds_video_model'
const getVideoKey = () => { try { return localStorage.getItem(VIDEO_KEY_LS) || '' } catch { return '' } }
const setVideoKey = (k) => { try { k ? localStorage.setItem(VIDEO_KEY_LS, k) : localStorage.removeItem(VIDEO_KEY_LS) } catch { /* 忽略 */ } }
const getVideoLabel = () => { try { return localStorage.getItem(VIDEO_KEY_LS + '_label') || '' } catch { return '' } }

function StageNav({ stage, setStage, hasProject = false, openSettings }) {
  return (
    <div className="stage-nav">
      {STAGES.map(s => {
        // 未选项目时除「项目」外的页面都不可进入，点进去只会看到空提示
        const locked = !s.enabled || (!hasProject && s.key !== 'projects')
        return (
        <div key={s.key}
          className={`stage-item ${stage === s.key ? 'active' : ''} ${locked ? 'disabled' : ''}`}
          title={locked && s.key !== 'projects' ? '请先在「项目」页选择或新建项目' : ''}
          onClick={() => !locked && setStage(s.key)}>
          <span className="ico">{s.ico}</span><span className="lbl">{s.lbl}</span>
        </div>
        )
      })}
      {/* 后台配置：模型 / LoRA / 加速 / 服务地址的统一入口，常驻导航底部 */}
      <div className="stage-item stage-config" title="模型、LoRA、加速与服务地址"
        onClick={openSettings}>
        <span className="ico">⚙️</span><span className="lbl">配置</span>
      </div>
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
      {next
        ? <button onClick={() => setStage(next.key)}>{nextLabel || `下一步：${next.lbl} →`}</button>
        : <span className="wizard-end">✓ 流程已完成</span>}
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
      <div className="grid project-grid">
        {projects.map(p => (
          <div key={p.id} className="asset-card project-card" onClick={() => selectProject(p.id)}>
            <div className="project-top">
              <div className="project-badge">{p.name.slice(0, 1)}</div>
              <div style={{ minWidth: 0 }}>
                <div className="name">{p.name}</div>
                <div className="project-meta">创建于 {p.created_at.slice(0, 10)}</div>
              </div>
            </div>
            <div className="desc project-desc">{p.description || '—'}</div>
            <div className="project-actions">
              <button className="small ghost" onClick={e => { e.stopPropagation(); selectProject(p.id) }}>进入工作台 →</button>
              <button className="small ghost danger" title="删除项目及其全部数据"
                onClick={e => { e.stopPropagation(); setDelMsg(''); setConfirmDel({ id: p.id, name: p.name }) }}>删除</button>
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
  const [vmodels, setVmodels] = useState([])
  const [vkey, setVkey] = useState(getVideoKey())
  useEffect(() => {
    (async () => {
      try {
        const d = await get('/models')
        const list = d.models || []
        setVmodels(list)
        // 后端下架的档位（如没有工作流模板的 vid_wan_i2v_aio）不能留在 localStorage：
        // 否则下拉显示空白、请求还把旧 key 发上去，视频跑到 ComfyUI 才报模板/节点错。
        const k = getVideoKey()
        if (k && !list.some(x => x.key === k)) { setVideoKey(''); setVkey('') }
      } catch { /* 老后端无此端点时保持空 */ }
    })()
  }, [])
  const pickVideo = (k) => {
    setVkey(k); setVideoKey(k)
    const m = vmodels.find(x => x.key === k)
    try { localStorage.setItem(VIDEO_KEY_LS + '_label', m ? m.label : '') } catch { /* 忽略 */ }
  }
  const go = async (kind, label, body = {}) => {
    setBusy(kind); setMsg(`${label}：任务已排队（GPU 串行执行，进度见底部任务栏）…`)
    try {
      const r = await post(`/episodes/${episodeId}/${kind}`, vkey ? { ...body, model_key: vkey } : body)
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
    <div className="batch-bar">
      <div className="batch-row">
        <span className="batch-label">视频档</span>
        <select className="batch-select" value={vkey} onChange={e => pickVideo(e.target.value)}
          title="单镜「生成视频」/ 批量视频 / 向后重链 / 一键全流程 统一按此档出视频；默认档在 models.yaml defaults 里改">
          <option value="">默认档（后端配置）</option>
          {vmodels.map(m => (
            <option key={m.key} value={m.key}>{m.label}{m.default ? ' · 默认' : ''}</option>
          ))}
        </select>
        <span className="batch-div" />
        <span className="batch-label">批量补缺</span>
        <button className="small ghost" disabled={!!busy} title="为所有缺首帧的镜头批量生成首帧" onClick={() => go('batch-frames', '批量首帧')}>🖼 补首帧</button>
        <button className="small ghost" disabled={!!busy} title="为所有已出首帧、缺视频的镜头批量生成视频" onClick={() => go('batch-videos', '批量视频')}>🎥 补视频</button>
        <button className="small ghost" disabled={!!busy} title="场景切换边界：上镜末帧+下镜首帧双帧 i2v 生成 1-2s 过渡镜（需两侧产物齐全，成片拼接时自动插入）"
          onClick={() => go('batch-transitions', '转场镜')}>🪄 转场镜</button>
        <span className="batch-div" />
        <span className="batch-label">全链路</span>
        <button className="small accent" disabled={!!busy} onClick={() => go('full-pipeline', '一键全流程')}>⚡ 一键全流程</button>
        <button className="small ghost danger" disabled={!!busy} title="从第 1 镜开始逐镜用上镜视频末帧重绘下镜首帧再出视频，全链衔接+人物外观继承（覆盖所有镜的现有首帧和视频）"
          onClick={() => { if (confirm('⛓ 全链重刷：从第 1 镜起向后连锁重生成所有镜头（末帧接力），现有首帧和视频全部被覆盖，约 40-60 分钟。确定？')) go('rechain-from', '全链重刷', { from_idx: 1 }) }}>⛓ 全链重刷</button>
      </div>
      <div className="batch-hint">已有产物的镜头自动跳过，可中断后重跑；重链类任务断链即停，修复后可从断点镜「向后重链」续跑</div>
      {msg && <div className="batch-hint" style={{ color: '#8fb8ff' }}>{msg}</div>}</div>
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
  const isVoice = wizardStage === 'voice'
  const voicePanel = (
    <div className="voice-panel">
      <div className="section-head" style={{ margin: '0 0 6px' }}>
        <h3>音色分配</h3>
        <span className="section-hint">试听 → 选择 → 自动保存锁定给该角色（未全部锁定前不能生成配音）</span>
      </div>
      <div className="voice-row">
        <span className="voice-name">旁白 / 无前缀台词</span>
        <VoiceSelect value={narrator} onChange={e => saveNarrator(e.target.value)} />
        <button className="small ghost" onClick={() => preview(narrator, 'narrator')}>{previewing === 'narrator' ? '…' : '🔊 试听'}</button>
      </div>
      {characters.map(c =>
        <div key={c.id} className="voice-row">
          <span className={`voice-name ${c.voice ? '' : 'unlock'}`}>{c.name}{!c.voice && <em>未锁定</em>}</span>
          <VoiceSelect value={c.voice} genderHint={guessGender(c)} onChange={e => saveVoice(c.id, e.target.value)} />
          <button className="small ghost" onClick={() => preview(c.voice, c.id)}>{previewing === c.id ? '…' : '🔊 试听'}</button>
        </div>)}
    </div>
  )
  const voiceGaps = [
    missingVoices.length ? `${missingVoices.length} 个角色未锁定音色` : '',
    narrator ? '' : '旁白未锁定音色',
  ].filter(Boolean).join('、')
  return (
    <div>
      <div className="page-title">{isVoice ? '配音' : '成片'} · {project.name}</div>
      <div className="page-sub">{isVoice
        ? '按角色锁定音色 → 台词逐句配音（edge-tts 在线，零显存）；锁定完整后可到「成片」页合成'
        : '逐镜视频无损拼接 → 台词配音混入 → SRT 字幕生成并烧录（NVENC 硬编）'}</div>
      {!!episodes.length &&
        <div className="row" style={{ alignItems: 'center' }}>
          <label style={{ margin: 0 }}>剧集</label>
          <select value={selId || ''} onChange={e => setSelId(Number(e.target.value))} style={{ maxWidth: 420 }}>
            {episodes.map(e => <option key={e.id} value={e.id}>第 {e.idx} 集 · {e.title || '（未命名）'}</option>)}
          </select>
        </div>}
      {!episodes.length && <div className="page-sub">本项目还没有剧集。</div>}

      {selId && !!shots.length && (
        <div className="section-head" style={{ marginTop: 16 }}>
          <h3>时间线粗剪<em>（共 {totalDur}s）</em></h3>
          <span className="section-hint">绿=有视频 · 黄=仅首帧 · 红=未制作，宽度≈时长</span>
        </div>)}
      {selId && !!shots.length &&
        <div className="shot-timeline">
          {shots.map(s =>
            <div key={s.id} title={`第 ${s.idx} 镜 · ${Number(s.duration) || 5}s · ${s.dialogue || '（无台词）'}`}
                 className={`shot-seg ${s.video_path ? 'done' : s.first_frame_path ? 'half' : 'bare'}`}
                 style={{ flexGrow: Number(s.duration) || 5 }}>
              {s.idx}
            </div>)}
        </div>}

      {isVoice ? voicePanel : (
        <details className="voice-fold">
          <summary>音色分配{voicesReady
            ? <span className="fold-ok">已全部锁定</span>
            : <span className="fold-warn">{voiceGaps}</span>}</summary>
          {voicePanel}
        </details>)}

      {selId &&
        <div className="export-card">
          <div className="export-stats">
            本集镜头 <b>{shots.length}</b> 个 · 已出视频 <b>{withVideo.length}</b> 个 · 有台词 <b>{shots.filter(s => s.dialogue).length}</b> 个
            {shots.length > withVideo.length && <span style={{ color: '#e9b949' }}>　（{shots.length - withVideo.length} 个镜头未出视频，将跳过）</span>}
          </div>
          <div className="ops-row">
            {isVoice
              ? <button className="small accent" disabled={!selId || busy || !shots.some(s => s.dialogue) || !voicesReady}
                  title={voicesReady ? '' : '先把每个角色和旁白的音色试听并锁定'}
                  onClick={doTts}>{busy === 'tts' ? '配音中…' : '🎙 生成台词配音'}</button>
              : <button className="small accent" disabled={!selId || busy || !withVideo.length} onClick={doExport}>{busy === 'export' ? '合成中…' : '🎬 合成成片'}</button>}
            {isVoice
              ? <button className="small ghost" disabled={!selId || busy || !withVideo.length} onClick={doExport}>{busy === 'export' ? '合成中…' : '🎬 去合成成片'}</button>
              : <button className="small ghost" disabled={!selId || busy || !shots.some(s => s.dialogue) || !voicesReady}
                  title={voicesReady ? '' : '先把每个角色和旁白的音色试听并锁定'}
                  onClick={doTts}>{busy === 'tts' ? '配音中…' : '🎙 重新配音'}</button>}
            <span className="ops-div" />
            <button className="small ghost" disabled={!selId || !!busy || !withVideo.length} onClick={() => doExportDraft('export-jianying', '剪映草稿')}>✂ 剪映草稿</button>
            <button className="small ghost" disabled={!selId || !!busy || !withVideo.length} onClick={() => doExportDraft('export-fcpxml', 'FCPXML')}>🎞 FCPXML</button>
          </div>
          {!voicesReady && <div className="batch-hint" style={{ color: '#e9b949' }}>{voiceGaps}</div>}
          {msg && <div className="batch-hint" style={{ color: '#9dc0ff' }}>{msg}</div>}
        </div>}

      {(status?.jianying || status?.fcpxml) &&
        <div className="row" style={{ gap: 14, margin: '6px 0' }}>
          {status.jianying && <a href={status.jianying} download="draft_content.json">⬇ 剪映草稿 draft_content.json</a>}
          {status.fcpxml && <a href={status.fcpxml} download="timeline.fcpxml">⬇ FCPXML</a>}
        </div>}

      {status?.final_ready &&
        <div className="preview-card">
          <div className="section-head" style={{ margin: '0 0 8px' }}><h3>成片预览</h3></div>
          <video controls src={status.final_file} className="preview-video" />
          {status.srt_ready && <div style={{ marginTop: 8 }}>
            <a href={status.srt_file} download="subtitle.srt">⬇ 下载 SRT 字幕</a>
          </div>}
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
      if (kind === 'video' && getVideoKey()) payload.model_key = getVideoKey()
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
      const r = await post(`/episodes/${episodeId}/rechain-from`,
        getVideoKey() ? { from_idx: fromIdx, model_key: getVideoKey() } : { from_idx: fromIdx })
      setGenMsg(`向后重链任务 #${r.task_id} 已入队（以第 ${fromIdx - 1} 镜为锚点，从第 ${fromIdx} 镜起：末帧→接力首帧→视频 连锁，断链即停），进度见底部任务栏`)
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
  // 运动动作控制编辑窗：身体部位级动作描述（静态姿态锚 + 视频运动 token）
  const [motionFor, setMotionFor] = useState(null)
  const [motionDraft, setMotionDraft] = useState({})
  const openMotion = (s) => { setMotionFor(s.id); setMotionDraft({ ...(s.motion || {}) }) }
  // 导演台（摄像机控制 / 运镜预设）
  const [directorFor, setDirectorFor] = useState(null)
  const saveMotion = async () => {
    try {
      await patch(`/shots/${motionFor}`, { motion: motionDraft })
      await post(`/episodes/${episodeId}/rebuild-prompts`, {})
      setMotionFor(null); load(); setGenMsg('动作控制已保存，全部提示词已重组装生效')
    } catch (e) { alert('保存失败：' + e.message) }
  }
  const refImg = (p, size, style) => p
    ? <img src={`/api/asset-file-by-path?path=${encodeURIComponent(p)}`} style={{ width: size, height: size * 1.25, objectFit: 'cover', borderRadius: 4, ...(style || {}) }} />
    : <div style={{ width: size, height: size * 1.25, border: '1px dashed var(--border-strong)', borderRadius: 4, fontSize: 10, color: 'var(--dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>无</div>

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
    <div className="shots-wrap">
    <div className="section-head" style={{ marginTop: 8 }}>
      <h3>镜头时间轴<em>（{shots.length} 镜 · 需出尾帧 {endCount} 镜）</em></h3>
      <span className="section-hint">逐镜制作：参考图、视频、操作都在本卡内，哪镜有问题单独重跑哪镜</span>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
        <button className="small ghost"
          onClick={async () => { await post(`/episodes/${episodeId}/rebuild-prompts`, {}); load() }}>重组装提示词</button>
        <button className="small ghost" onClick={load}>刷新</button>
      </div>
    </div>

    {/* mini 时间轴：点击色块跳转到对应镜头卡 */}
    <div className="shot-timeline">
      {shots.map(s =>
        <div key={s.id} title={`第 ${s.idx} 镜 · ${Number(s.duration) || 5}s · ${s.dialogue || '（无台词）'}`}
          onClick={() => jumpTo(s.idx)}
          className={`shot-seg ${s.video_path ? 'done' : s.first_frame_path ? 'half' : 'none'}`}
          style={{ flexGrow: Number(s.duration) || 5 }}>
          {s.idx}
        </div>)}
    </div>

      {shots.map(s => { const st = s.video_path ? 'done' : s.first_frame_path ? 'half' : 'none'; return (
        <div key={s.id} id={`shot-card-${s.idx}`} className="shot-card">
          {/* 卡片头 */}
          <div className="shot-head">
            <span className={`shot-idx ${st}`}>#{s.idx}</span>
            <span className="shot-spec">{Number(s.duration) || 5}s · {s.shot_size}
              {s.framing_end && s.framing_end !== s.shot_size ? ` → ${s.framing_end}` : ''} · {s.camera_move || '固定'}/{s.camera_speed || 'normal'}</span>
            <span className="shot-scene">{s.scene_name}</span>
            <div className="name-row">
              {(s.characters || []).length
                ? (s.characters || []).map(c => <span key={c} className="tag chip-role">{c}</span>)
                : <span className="tag">空镜</span>}
              {(s.props || []).map(p => <span key={p} className="tag chip-prop">{p}</span>)}
            </div>
            <span className={`badge ${st === 'done' ? 'done' : st === 'half' ? 'paused' : 'pending'}`} style={{ marginLeft: 'auto' }}
              title={`内部状态 ${s.status || 'planned'}`}>
              {st === 'done' ? '已出片' : st === 'half' ? '仅首帧' : '待生成'}
            </span>
          </div>
          {s.dialogue ? <div className="shot-dialogue">台词：{s.dialogue}{s.sfx ? <span style={{ color: '#8e97a6' }}>　音效：{s.sfx}</span> : ''}</div> : null}

          {/* 主体：参考图清单 | 视频 | 操作 */}
          <div className="shot-body">
            <div className="shot-media">
              {/* 有视频时不再单独显示首帧缩略图：视频第一帧即首帧，避免重复占位 */}
              {!s.video_path &&
                <div className="shot-thumb-wrap">
                  <div>首帧{s.first_frame_path ? '' : '（未生成）'}</div>
                  {s.first_frame_path
                    ? <img src={`/api/shots/${s.id}/frame-file?which=first&t=${Date.now()}`} className="shot-thumb"
                        onClick={() => window.open(`/api/shots/${s.id}/frame-file?which=first`)} />
                    : <div className="shot-empty" style={{ width: 128, height: 72 }}>待生成</div>}
                </div>}
              <div className="shot-thumb-wrap">
                <div>尾帧{s.end_frame_path ? '' : (s.needs_end_frame ? '（未生成）' : '（固定镜·无需）')}</div>
                {s.end_frame_path
                  ? <img src={`/api/shots/${s.id}/frame-file?which=end&t=${Date.now()}`} className="shot-thumb"
                      onClick={() => window.open(`/api/shots/${s.id}/frame-file?which=end`)} />
                  : <div className="shot-empty" style={{ width: 128, height: 72 }}>
                      {s.needs_end_frame ? '待生成' : <><span>固定镜无需尾帧</span><span style={{ fontSize: 10 }}>接力自动抽视频末帧</span></>}
                    </div>}
              </div>
              {s.scene_anchor_path &&
                <div className="shot-thumb-wrap">
                  <div style={{ color: '#e0b34a' }}>场景锚 ⚓</div>
                  <img src={`/api/asset-file-by-path?path=${encodeURIComponent(s.scene_anchor_path)}`}
                    className="shot-thumb" style={{ width: 86, height: 72, objectFit: 'cover', borderColor: 'rgba(224,179,74,.45)' }}
                    onClick={() => window.open(`/api/asset-file-by-path?path=${encodeURIComponent(s.scene_anchor_path)}`)} />
                </div>}
              {grids[s.id] ? (
                <div className="shot-thumb-wrap">
                  <div>宫格候选</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 36px)', gap: 3 }}>
                    {grids[s.id].map((c, i) => (
                      <img key={i} src={`/api/shots/${s.id}/cell-file?i=${i}`}
                        onClick={() => pickCell(s.id, c)} title="设为首帧"
                        style={{ width: 36, display: 'block', borderRadius: 4, border: '1px solid var(--border)', cursor: 'pointer' }} />
                    ))}
                  </div>
                </div>) : null}
            </div>

            <div className="shot-thumb-wrap">
              <div>视频{s.video_path ? '' : '（未生成）'}</div>
              {s.video_path
                ? <video controls src={`/api/shots/${s.id}/video-file`} title="视频第一帧即本镜首帧" className="shot-video" />
                : <div className="shot-empty" style={{ width: 208, height: 74 }}>
                    {s.first_frame_path ? '有首帧，可生成视频' : '需先生成首帧'}</div>}
            </div>

            <div className="shot-ops">
              <div className="ops-row">
                <span className="ops-label" title="IPAdapter 锁脸强度">锁脸
                  <select value={ipaW} onChange={e => setIpaW(Number(e.target.value))} style={{ marginLeft: 4, width: 'auto', fontSize: 11, padding: '2px 16px 2px 4px', backgroundPosition: 'right 2px center' }}>
                    <option value={0.55}>0.55</option><option value={0.70}>0.70</option><option value={0.85}>0.85</option>
                  </select>
                </span>
                <button className="small" disabled={!!busy[s.id]}
                  onClick={() => gen(s.id, 'frame', { frame_type: 'first' })}>
                  {busy[s.id] === 'frame' ? '提交中…' : '🖼 首帧'}
                </button>
                {s.needs_end_frame &&
                  <button className="small ghost" disabled={!!busy[s.id]}
                    onClick={() => gen(s.id, 'frame', { frame_type: 'end' })}>尾帧</button>}
                <button className="small" disabled={!!busy[s.id] || !s.first_frame_path}
                  title={s.first_frame_path ? '' : '需先生成首帧'}
                  onClick={() => gen(s.id, 'video', { duration: s.duration })}>
                  {busy[s.id] === 'video' ? '提交中…' : '🎥 视频'}
                </button>
                <button className="small ghost" disabled={!!busy[s.id] || !s.first_frame_path || !(s.dialogue || '').trim()}
                  title={!(s.dialogue || '').trim() ? '需先在参数区填台词（角色名（语气）：台词）' : '台词配音驱动口型：重新生成本镜视频，口型/表情跟音频走'}
                  onClick={() => genTalk(s.id, s.idx)}>🗣 说话镜</button>
                {isAnime && <button className="small ghost" disabled={!!busy[s.id]}
                  onClick={() => genGrid(s.id)}>九宫格</button>}
              </div>
              <div className="ops-row ops-sub">
                <button className="small ghost" onClick={() => openRefs(s.id)}
                  title="查看本镜生成实际引用的角色/场景资产图，可手动指定换用">🔍 参考{(s.ref_overrides && Object.keys(s.ref_overrides).length) ? ' ✓' : ''}</button>
                <button className="small ghost" onClick={() => openMotion(s)}
                  title="运动动作控制：身体姿态/手部动作/表情状态/视线/动作幅度/次级联动——把“做什么”钉到“怎么做”，压随机性">🎬 动作{Object.keys(s.motion || {}).length ? ' ✓' : ''}</button>
                <button className="small ghost" onClick={() => setDirectorFor(s)}
                  title="导演台：景别/机位/运镜/速度/焦段/焦点/转场按钮 + 运镜预设，点一下即写入并重算提示词">🎥 摄像</button>
                <span className="ops-div" />
                <button className="small ghost" disabled={!s.needs_end_frame && !s.video_path}
                  title="用本镜末帧重绘下一镜首帧，构图光影连贯"
                  onClick={() => chainNext(s.id)}>⏭ 接力</button>
                <button className="small ghost"
                  title={`从本镜起向后连锁重生成：本镜首帧以上一镜末帧重绘覆盖，逐镜 末帧→首帧→视频 向后传递（衔接+人物一致）。断链即停`}
                  onClick={() => { if (confirm(`⛓ 以第 ${s.idx} 镜为锚点向后重链：第 ${s.idx} 镜本身保持不动，从第 ${s.idx + 1} 镜起所有镜的首帧和视频用末帧接力连锁重新生成，不可自动恢复。确定？`)) rechain(s.idx + 1) }}>⛓ 向后重链</button>
                <button className="small ghost" disabled={!s.video_path}
                  title="视频不够长：提末帧续写 3s 再拼接"
                  onClick={() => extendVideo(s.id)}>⏩ 续写</button>
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
      )})}
      {genMsg ? <div className="page-sub">{genMsg}</div> : null}
      {/* 参考溯源窗口：本镜生成用了哪些资产图 + 手动换 */}
      {refsFor && refsData && (
        <div className="modal-mask" onClick={() => { setRefsFor(null); load() }}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ width: 'min(780px, 92vw)', maxHeight: '82vh' }}>
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
                    当前：{c.used_path ? (c.source === 'manual' ? '手动指定'
                      : c.source === 'locked' ? '角色默认脸锁（📌 已钉死版本）'
                      : `自动择优（${c.used_kind}）`) : '无可用人像参考'}
                  </span>
                  {c.source === 'manual' &&
                    <button className="small ghost" style={{ marginLeft: 8 }}
                      onClick={() => setRef(refsFor, c.name, '')}>清除指定</button>}
                  {c.used_path && c.character_id && c.source !== 'locked' &&
                    <button className="small ghost" style={{ marginLeft: 8 }} title="钉死这张图为该角色所有镜头的 IPAdapter 参考（面部 100% 一致），其他镜头不再随版本漂移"
                      onClick={async () => {
                        try { await post(`/characters/${c.character_id}/face-lock`, { path: c.used_path }); load(); setGenMsg(`已锁定 ${c.name} 默认参考：该角色全部镜头统一用这张脸`) } catch (e) { alert('锁定失败：' + e.message) }
                      }}>📌 设为默认参考</button>}
                  {c.source === 'locked' &&
                    <button className="small ghost" style={{ marginLeft: 8 }} title="解除后回到自动择优"
                      onClick={async () => {
                        try { await post(`/characters/${c.character_id}/face-lock`, { path: '' }); load(); setGenMsg(`已解除 ${c.name} 默认脸锁`) } catch (e) { alert('解除失败：' + e.message) }
                      }}>🔓 解除脸锁</button>}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  <div title="当前使用">
                    {refImg(c.used_path, 64, { border: '2px solid #2a7' })}
                    <div style={{ fontSize: 10, color: '#2a7', textAlign: 'center' }}>使用中</div>
                  </div>
                  {c.candidates.filter(x => x.path !== c.used_path).map((x, i) => (
                    <div key={i} title={`点击换用（${x.kind}）`} style={{ cursor: 'pointer' }}
                      onClick={() => setRef(refsFor, c.name, x.path)}>
                      {refImg(x.path, 56, { border: '1px solid var(--border-strong)' })}
                      <div style={{ fontSize: 10, color: 'var(--dim)', textAlign: 'center' }}>{x.kind}</div>
                    </div>))}
                  {!c.candidates.length ? <span style={{ fontSize: 11, color: 'var(--dim)' }}>（角色资产库暂无单人参考图）</span> : null}
                </div>
              </div>))}
            <div style={{ marginTop: 12, borderTop: '1px solid #2a3a4a', paddingTop: 8 }}>
              <div style={{ fontSize: 12 }}>
                <b>场景锚⚓ {refsData.scene.name || '（未设置场景）'}</b>
                <span style={{ marginLeft: 8, color: 'var(--dim)' }}>
                  当前：{refsData.scene.used_path ? (refsData.scene.source === 'manual' ? '手动指定'
                    : refsData.scene.source === 'anchor' ? '场景锚点（资产页选定）'
                    : '自动回退（iso 布局图/场景图，未手动设锚）') : '无锚图'}
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
                    {refImg(x.path, 56, { border: '1px solid var(--border-strong)' })}
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
      {motionFor != null && (
        <div className="modal-mask" onClick={() => setMotionFor(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ width: 'min(580px, 92vw)', fontSize: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <b>🎬 运动动作控制</b>
              <span style={{ color: 'var(--dim)', fontSize: 11 }}>英文填写（CLIP/Wan 只认英文）；保存后自动重组装提示词</span>
              <button className="small ghost" style={{ marginLeft: 'auto' }} onClick={() => setMotionFor(null)}>关闭</button>
            </div>
            {[['posture', '身体姿态', 'standing with weight on one leg / seated, leaning forward / crouched beside the desk'],
              ['gesture', '手部动作（手级细节）', 'hands clasped tightly, knuckles white / one hand braced on the table edge'],
              ['expression', '表情状态（微表情）', 'jaw clenched, breathing shallow / faint relieved smile, eyes still wary'],
              ['gaze', '视线方向', 'eyes fixed on the contract / looking past the window, unfocused / glancing back over the shoulder'],
              ['secondary', '次级联动（物理规律）', 'hair strands drifting with the step, coat hem swaying / breath fog in cold air']].map(([k, zh, hint]) => (
              <div key={k} style={{ marginTop: 8 }}>
                <div style={{ color: 'var(--dim)' }}>{zh} <span style={{ fontSize: 10 }}>示例：{hint}</span></div>
                <input value={motionDraft[k] || ''} placeholder={hint}
                  onChange={e => setMotionDraft(d => ({ ...d, [k]: e.target.value }))}
                  style={{ width: '100%', fontSize: 12, marginTop: 2 }} />
              </div>))}
            <div style={{ marginTop: 8, color: 'var(--dim)' }}>动作幅度（视频运动强度）</div>
            <select value={motionDraft.intensity || ''} style={{ fontSize: 12, marginTop: 2 }}
              onChange={e => setMotionDraft(d => ({ ...d, intensity: e.target.value }))}>
              <option value="">（默认，不限定）</option>
              <option value="subtle">subtle 轻微（对话/凝视）</option>
              <option value="natural">natural 自然（日常动作）</option>
              <option value="strong">strong 大（冲突/奔跑）</option>
            </select>
            <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
              <button className="small" onClick={saveMotion}>保存并重组装提示词</button>
              <button className="small ghost" onClick={() => setMotionDraft({})}>清空</button>
            </div>
          </div>
        </div>)}
      {directorFor && <DirectorPanel shot={directorFor}
        onClose={() => setDirectorFor(null)}
        onApplied={load} />}
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
  // 大纲输入：多行 textarea + 全窗口弹层 + 上传 txt 全文，均不设字数上限
  const [ideaFull, setIdeaFull] = useState(false)
  const [txtMsg, setTxtMsg] = useState('')
  // 分集列表分页：每页 5 集
  const [epPage, setEpPage] = useState(0)
  const [script, setScript] = useState('')
  const [breakdown, setBreakdown] = useState(null)
  const [checks, setChecks] = useState({})
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [presets, setPresets] = useState({})
  const [genres, setGenres] = useState({})
  const [styleLibOpen, setStyleLibOpen] = useState(false)
  // 风格锁当前值：弹窗套用后要立刻反映到信息条，不能只 mutate project 对象（React 不会重渲染）
  const [curPresetKey, setCurPresetKey] = useState(project.style_preset || '')

  // 全量预设（含 hidden 标记）：信息条要能显示"当前用的正好是暂不适用风格"这种情况
  useEffect(() => { api('/style-presets?include_hidden=true').then(setPresets).catch(() => {}) }, [])
  useEffect(() => { api('/style-genres').then(setGenres).catch(() => {}) }, [])

  // 风格锁：下拉已降级为只读信息条，切换统一走风格库弹窗（弹窗内 apply 有失败反馈）
  const currentPreset = curPresetKey || project.style_preset || 'anime_2d'
  const presetEntries = Object.entries(presets)
  const visiblePresetEntries = presetEntries.filter(([, v]) => !v.hidden)
  const curPresetHidden = !!presets[currentPreset]?.hidden
  // 全片光影 / 色彩预设（对齐 RHTV 节点底部滤镜条）：只写提示词词块，
  // 后端零 LLM 重算全项目所有镜头，不调云端、不耗 token。
  const [lgMeta, setLgMeta] = useState(null)
  const [grade, setGrade] = useState(project.light_grade || '')
  const [gradeMsg, setGradeMsg] = useState('')
  useEffect(() => {
    loadDirectorMeta().then(m => setLgMeta(m)).catch(() => {})
  }, [])
  const saveGrade = async (v) => {
    setGrade(v)
    const zh = ((lgMeta?.light_grades || []).find(x => x.v === v) || {}).zh || v
    try {
      const r = await post(`/projects/${project.id}/light-grade`, { grade: v })
      project.light_grade = v
      setGradeMsg(v
        ? `✔ 全片切到「${zh}」：${r.episodes} 集 / ${r.shots} 镜提示词已重算（本地模型执行，未耗 token）`
        : `✔ 已关闭全片滤镜：${r.episodes} 集 / ${r.shots} 镜回到各镜头自己的光位描述`)
    } catch (e) { setGradeMsg('应用失败：' + e.message) }
  }
  const saveGenre = async (key) => { await put(`/projects/${project.id}`, { genre: key }); project.genre = key }
  const currentGenre = project.genre || ''
  const [bridge, setBridge] = useState(project.transition_bridge === 1)
  const [fx, setFx] = useState(project.transition_fx || '')
  const toggleBridge = async (v) => { setBridge(v); await put(`/projects/${project.id}`, { transition_bridge: v ? 1 : 0 }) }
  const saveFx = async (v) => { setFx(v); await put(`/projects/${project.id}`, { transition_fx: v }) }
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

  // 上传本地 txt/md 读全文填入：优先 UTF-8，替换符过多则按 GB18030 重解（国内 txt 多为 GBK）
  const loadIdeaTxt = async (e) => {
    const f = e.target.files && e.target.files[0]
    e.target.value = ''                       // 清空 value，允许重复选同一个文件
    if (!f) return
    try {
      const buf = await f.arrayBuffer()
      let text = new TextDecoder('utf-8').decode(buf)
      if ((text.match(/\uFFFD/g) || []).length > 20) {
        try { text = new TextDecoder('gb18030').decode(buf) } catch { /* 浏览器不支持该编码则保持 UTF-8 结果 */ }
      }
      text = text.replace(/\r\n?/g, '\n').trim()
      if (!text) { setTxtMsg(`「${f.name}」里没有读到文本`); return }
      setIdea(text)                           // 直接替换为文档全文，后续可继续编辑
      setTxtMsg(`已读取「${f.name}」：${text.length.toLocaleString()} 字（覆盖原内容，可编辑后再生成）`)
    } catch (err) {
      setTxtMsg('读取失败：' + err.message)
    }
  }

  useEffect(() => {
    if (!ideaFull) return
    const h = (e) => { if (e.key === 'Escape') setIdeaFull(false) }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [ideaFull])

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
  const MODE_LABEL = { sheet: '人物设计图 768×1024', single: '单人立绘竖版', board: '角色板（全要素）' }

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
                        {/* 【硬性要求】角色资产必须"人物设计图"版式，选项已锁死 */}
                        <select value="sheet" disabled style={{ width: '100%' }} title="角色资产硬性要求：人物设计图（概念设定稿）">
                          <option value="sheet">人物设计图 768×1024</option>
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
        <label>全局风格锁（{visiblePresetEntries.length} 种预设，注入所有剧本拆解与生图提示词，保证全片画风统一）</label>
        <div className="style-lock-bar" role="button" tabIndex={0}
          onClick={() => setStyleLibOpen(true)}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setStyleLibOpen(true) } }}
          title="只读展示当前风格锁；点「打开风格库」或本条即可切换">
          <span className="style-lock-name">{presets[currentPreset]?.label || currentPreset}</span>
          {curPresetHidden && <span className="tag" style={{ fontSize: 10 }}>暂不适用</span>}
          <span className="style-lock-meta">
            {[presets[currentPreset]?.category, presets[currentPreset]?.family].filter(Boolean).join(' · ')}
          </span>
          <button className="small ghost" onClick={e => { e.stopPropagation(); setStyleLibOpen(true) }}>🎨 打开风格库</button>
        </div>
        <div className="page-sub" style={{ fontSize: 12, marginTop: 6 }}>锁词：{presets[currentPreset]?.style_lock}</div>
        <div className="page-sub" style={{ fontSize: 12, marginTop: 2 }}>视频动态策略：{presets[currentPreset]?.motion_hint}</div>
        <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--line)' }}>
          <label style={{ fontSize: 12 }}>全片光影 / 色彩（滤镜层，纯提示词 · 不耗 token · 不调云端）</label>
          <div className="row" style={{ marginTop: 4 }}>
            <select value={grade} onChange={e => saveGrade(e.target.value)} style={{ flex: 1 }}>
              <option value="">自动（不加滤镜，按每镜自己的光位描述）</option>
              {(lgMeta?.light_grade_groups || []).map(g => (
                <optgroup key={g} label={`── ${g} ──`}>
                  {(lgMeta.light_grades || []).filter(x => x.group === g)
                    .map(x => <option key={x.v} value={x.v}>{x.zh} — {x.hint}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="page-sub" style={{ fontSize: 11, marginTop: 3 }}>
            {gradeMsg || (grade
              ? '点一次即全项目重算；单个镜头可在「🎥 摄像」里单独覆盖，覆盖优先于全片'
              : '不改画面内容，只改打光与调色倾向；改完需重新生成首帧/视频才落到画面上')}
          </div>
        </div>
        {/* 生成设置：两列网格，每项「标题 → 控件 → 说明」，不再把 7 个开关挤成一行 */}
        <div className="settings-grid">
          <div className="field full">
            <div className="field-label">题材词库</div>
            <select value={currentGenre} onChange={e => saveGenre(e.target.value)}>
              <option value="">不挂题材词库（纯风格）</option>
              {Object.entries(genres).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
            <div className="field-hint">
              红果爆款反向解析，注入镜头 mood + 名场面钩子
              {genres[currentGenre]?.sample_setting ? ` · ${genres[currentGenre].sample_setting}` : ''}
            </div>
          </div>

          <div className="field">
            <div className="field-label">全局画幅</div>
            <select value={aspect} onChange={e => setAspectRatio(e.target.value)}>
              {ASPECTS.map(a => <option key={a.v} value={a.v}>{a.label}</option>)}
            </select>
            <div className="field-hint">场景 / 道具 / 分镜首尾帧 / 宫格统一跟随；角色定妆照固定竖版。只对之后的新生成生效。</div>
          </div>

          <div className="field">
            <div className="field-label">成片兜底转场</div>
            <select value={fx} onChange={e => saveFx(e.target.value)}>
              <option value="">不加（硬切）</option>
              <option value="fadeblack">黑场过渡</option>
              <option value="fadewhite">白闪过渡</option>
            </select>
            <div className="field-hint">只用于没有转场镜的场景切换边界。</div>
          </div>

          <div className="field">
            <label className={`switch-row ${bridge ? 'on' : 'off'}`}
              title="开启后：批量视频/一键全流程会在场景切换边界自动生成双帧过渡镜（上镜末帧→下镜首帧 i2v，1-2s），成片拼接时自动插入">
              <input type="checkbox" checked={bridge} onChange={e => toggleBridge(e.target.checked)} />
              <span>生成转场镜</span>
            </label>
            <div className="field-hint">场景切换处自动出 1–2s 双帧过渡镜（上镜末帧 → 下镜首帧），每条约 2 分钟，拼接时自动插入。</div>
          </div>

          <div className="field">
            <label className="switch-row" title="生活化瑕疵 + 真实光影 + 非模板姿态 + 规避过度渲染">
              <input type="checkbox" checked={lifelike} onChange={e => toggleLifelike(e.target.checked)} />
              <span>活人感机制</span>
            </label>
            <div className="field-hint">生活化瑕疵 + 真实光影 + 非模板姿态 + 规避过度渲染。</div>
          </div>

          <div className="field">
            <label className="switch-row" title="连角色设计图也加五官不完美；只建议分镜用，会牺牲跨集一致性">
              <input type="checkbox" checked={lifelikeFull} onChange={e => toggleLifelikeFull(e.target.checked)} />
              <span>全量瑕疵</span>
            </label>
            <div className="field-hint">连角色设计图也加五官不完美。只建议分镜用，会牺牲跨集一致性。</div>
          </div>

          <div className="field">
            <label className="switch-row" title="分级：场景/道具 ON；角色设计图 OFF，可手动单张微调">
              <input type="checkbox" checked={autoPolish} onChange={e => toggleAutoPolish(e.target.checked)} />
              <span>初图 10% 微调</span>
            </label>
            <div className="field-hint">分级执行：场景 / 道具 ON，角色设计图 OFF；可手动单张微调。</div>
          </div>

          {(presets[currentPreset]?.category || '').includes('动漫') && (
            <div className="field">
              <label className="switch-row" title="九宫格候选构图→裁单格作首帧；写实风格易糊，建议关闭">
                <input type="checkbox" checked={gridBoard} onChange={e => toggleGrid(e.target.checked)} />
                <span>宫格故事板</span>
              </label>
              <div className="field-hint">九宫格候选构图 → 裁单格作首帧。仅动漫风格建议开，写实易糊。</div>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="idea-bar">
          <div style={{ minWidth: 0 }}>
            <div className="field-label" style={{ fontSize: 13 }}>① 创意 / 大纲 → 生成分集</div>
            <div className="field-hint">一行一条也行，整段贴也行，字数不限；可上传 txt / md 全文直接填入。</div>
          </div>
          <div className="idea-tools">
            <label className="chip" title="读取本地 txt / md / log 全文填入输入框（自动识别 UTF-8 与 GBK）">
              📄 上传文档
              <input type="file" accept=".txt,.md,.markdown,.log,text/plain" style={{ display: 'none' }} onChange={loadIdeaTxt} />
            </label>
            <button className="ghost" style={{ padding: '5px 12px', fontSize: 12 }} onClick={() => setIdeaFull(true)}
              title="全窗口编辑：适合贴整本设定或几十集大纲">
              ⤢ 全窗口
            </button>
          </div>
        </div>
        <textarea className="idea-box" value={idea} onChange={e => setIdea(e.target.value)}
          placeholder={"例：\n1) 题材定位：男频穿越修仙 + AI外挂 + 都市智斗逆袭\n2) 核心卖点：绝症少年带毒舌AI用算力玩梗逆袭\n3) 世界观：灵气可数据化，推演要扣生机值"} />
        <div className="row" style={{ marginTop: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--dim)' }}>分集数量</span>
          <input type="number" min="1" max="60" value={nEp} onChange={e => setNEp(e.target.value)} style={{ width: 78 }} />
          <span style={{ fontSize: 12, color: 'var(--dim)' }}>{idea.trim() ? `${idea.length.toLocaleString()} 字` : '未填写'}</span>
          <button style={{ marginLeft: 'auto' }} disabled={busy || !idea.trim()} onClick={genOutline}>生成分集大纲</button>
        </div>
        {txtMsg && <div className="field-hint" style={{ marginTop: 8 }}>{txtMsg}</div>}
        {idea.length > 4000 && (
          <div className="field-hint" style={{ marginTop: 4 }}>提示：文本较长，本地模型上下文有限，超长部分可能被截断，建议 3000–4000 字内。</div>
        )}
      </div>

      {ideaFull && (
        <div className="modal-mask" onClick={e => { if (e.target === e.currentTarget) setIdeaFull(false) }}>
          <div className="modal-box">
            <div className="idea-bar">
              <div style={{ minWidth: 0 }}>
                <div className="field-label" style={{ fontSize: 16 }}>创意 / 大纲 · 全窗口编辑</div>
                <div className="field-hint">字数不限，可直接粘贴整篇设定；Esc 或点空白处关闭，内容实时同步到对话框。</div>
              </div>
              <div className="idea-tools">
                <label className="chip" title="读取本地 txt / md 全文填入（自动识别 UTF-8 与 GBK）">
                  📄 上传文档
                  <input type="file" accept=".txt,.md,.markdown,.log,text/plain" style={{ display: 'none' }} onChange={loadIdeaTxt} />
                </label>
                <button className="ghost" style={{ padding: '5px 12px', fontSize: 12 }} onClick={() => setIdeaFull(false)}>关闭 ✕</button>
              </div>
            </div>
            <textarea autoFocus className="idea-box-full" value={idea} onChange={e => setIdea(e.target.value)}
              placeholder="把整篇设定、人物小传、分集大纲直接贴进来…" />
            <div className="row" style={{ marginTop: 12, alignItems: 'center' }}>
              <span className="field-hint" style={{ margin: 0 }}>{idea.length.toLocaleString()} 字</span>
              <button style={{ marginLeft: 'auto' }} disabled={busy || !idea.trim()} onClick={() => { setIdeaFull(false); genOutline() }}>生成分集大纲</button>
            </div>
          </div>
        </div>
      )}

      <div className="row" style={{ alignItems: 'flex-start', gap: 16 }}>
        <div className="ep-pane">
          <div className="ep-pane-head">
            <label style={{ marginBottom: 0 }}>② 分集列表</label>
            {!!episodes.length && (
              <button className="small ghost" disabled={busy}
                onClick={continueOutline} title={`保留现有 ${episodes.length} 集，从第 ${episodes.length + 1} 集继续生成 10 集（含逐集 AI 剧本）`}>
                续写 +10 集
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
            <div className="row" style={{ marginTop: 10, gap: 7 }}>
              <button className="small ghost" onClick={writeScript} disabled={busy}>AI 写本集剧本</button>
              <button className="small ghost" onClick={saveScript} disabled={busy}>保存剧本</button>
              <button className="small accent" onClick={doBreakdown} disabled={busy || !script.trim()}>④ 结构化拆解 →</button>
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
      {styleLibOpen && <StyleLibraryModal project={project}
        onClose={() => setStyleLibOpen(false)}
        onApplied={k => { setCurPresetKey(k); setPresets(x => ({ ...x })) }} />}
      <WizardBar stage="script" setStage={setStage} nextLabel="下一步：查看资产 →" />
    </div>
  )
}

/* ---------- 资产编辑弹窗 ---------- */
function AssetEditor({ asset, models, onClose, refreshTasks, onDeleted, onTextEdit }) {
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
    ? [768, 1024]   // 【硬性要求】角色走"人物设计图"竖版稿（Qwen-Image 768×1024，约 40 秒）
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
      onClose(true, `重新渲染任务 #${r.task_id} 已入队（本地底模），完成后回到这里查看新版本；字不对就用卡片上的「📝 改字」局部微调`)
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
      <div className="modal modal-wide" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <div className="page-title">{ENTITY_LABEL[asset._etype]}资产调整 · {asset.name}</div>
          <button className="modal-x" title="关闭" onClick={() => onClose(false)}>✕</button>
        </div>
        <div className="asset-editor">
          <div className="asset-history">
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
          <div className="asset-form">
            <label>名称</label>
            <input value={name} onChange={e => setName(e.target.value)} />
            {Object.keys(slots).length ? (
              <>
                <label>结构化提示词槽位（改后自动按公式重组提示词，风格锁保持不变）</label>
                {role === 'portrait' && (
                  <>
                    <label>角色生成方式（人物设计图怎么出）</label>
                    <div className="row" style={{ marginBottom: 6 }}>
                      <select value={genMode} onChange={e => {
                        const gm = e.target.value
                        setGenMode(gm)
                        if (gm === 'layout' || gm === 'compose') { setW(1344); setH(768) }
                      }} style={{ flex: 1 }}>
                        <option value="auto">自动（Qwen-Image 整张设计稿：中心立绘 + 服装分层 + 表情头 + 材质特写｜768×1024，约 40 秒）</option>
                        <option value="layout">Qwen-Image 整张设计稿（同「自动」，指定走 Qwen 通道）</option>
                        <option value="compose">SDXL 三视角拼版（旧版式，与设计图冲突·不推荐）</option>
                      </select>
                    </div>
                    <div className="row" style={{ marginBottom: 6 }}>
                      <span style={{ color: 'var(--dim)', fontSize: 13 }}>版式：</span>
                      <select value="sheet" disabled style={{ flex: 1 }} title="角色资产硬性要求：人物设计图（概念设定稿）">
                        <option value="sheet">人物设计图 768×1024（概念设定稿 · 不可更改）</option>
                      </select>
                    </div>
                  </>
                )}
                {role === 'scene' && !('text_content' in slots) && (
                  <div className="row" style={{ marginBottom: 6 }}>
                    <span style={{ color: 'var(--dim)', fontSize: 13, whiteSpace: 'nowrap' }}>牌匾/招牌文字（可选）</span>
                    <input value={slots.text_content || ''} placeholder="门额上要写的字，如 青云宗 · 中文/英文都行"
                      onChange={e => setSlots(s => ({ ...s, text_content: e.target.value }))} style={{ flex: 1 }} />
                  </div>
                )}
                <div className="slot-grid">
                  {Object.entries(slots).map(([k, v]) => (
                    <div className="slot-cell" key={k}>
                      <span className="slot-label">{SLOT_ZH[k] || k}<em>{k}</em></span>
                      {k === 'ethnicity' ? (
                        <select value={v || ''} onChange={e => setSlots(s => ({ ...s, [k]: e.target.value }))}>
                          <option value="">（未指定）</option>
                          {ETHNICITIES.map(([ev, el]) => <option key={ev} value={ev}>{el}</option>)}
                        </select>
                      ) : (
                        <input value={v || ''} onChange={e => setSlots(s => ({ ...s, [k]: e.target.value }))} />
                      )}
                    </div>
                  ))}
                </div>
                <label style={{ marginTop: 8 }}>最终提示词（自动组装，可直接查看）</label>
                <textarea value={prompt} readOnly style={{ minHeight: 70, color: 'var(--dim)' }} />
                {role === 'portrait' && <CharacterAdjust slots={slots} onChange={setSlots} />}
              </>
            ) : (
              <>
                <label>图像提示词（改完可保存或直接重新渲染）</label>
                <textarea value={prompt} onChange={e => setPrompt(e.target.value)} style={{ minHeight: 110 }} />
              </>
            )}
            {(role === 'prop' || role === 'scene' || role === 'portrait') && (
              <div className="card" style={{ borderColor: 'var(--line)', marginTop: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent-strong)', marginBottom: 4 }}>
                  📝 图上的文字：局部改字，全本地
                </div>
                <div style={{ fontSize: 12, color: 'var(--dim)', lineHeight: 1.65 }}>
                  三类资产都支持在<b>同一张已生成的图上</b>框住文字区域重画——框外的纸纹、折痕、朱印、边框与光影一点不动，不耗 token、不调云端：
                  道具设计图改牌面/券面铭文，场景设计图改门额/牌匾/招牌，角色设计图改面板旁的手写标注与信息行。
                  画完会<b>自动判字</b>（本地 OCR 读数与原字逐字比对，零 token）：没读对就按生成情况重新框选再画，框逐步收紧、能定位到错字时只重写那一个字，默认最多 3 轮，落库交付其中最好的一轮。<span style={{ color: 'var(--dim)' }}>小提示：旧字的下半截若落在框外会留一道残笔，拖框时把下缘多留一点。</span>
                  {role === 'prop' && <div style={{ marginTop: 4 }}>
                    带文字道具在<b>生成时</b>就按语言自动分工：<b>中文</b>走 MOSS-Image SFT（8 步蒸馏，约 40 秒，毛笔字逐字准），
                    <b>英文</b>走 Ideogram 4 fp8（结构化 caption，英文单词一个不差）。英文档不支持局部重绘，改字会整图重出、构图可能变化。
                  </div>}
                </div>
                <div className="ops-row" style={{ marginTop: 6 }}>
                  <button className="small" disabled={!versions.length}
                    onClick={() => onTextEdit && onTextEdit(asset)}>📝 改字（框选局部重绘）</button>
                  {!versions.length && <span style={{ fontSize: 11, color: 'var(--dim)' }}>先渲染一张，再来改字</span>}
                </div>
              </div>
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
            <div className="ops-row" style={{ marginTop: 16 }}>
              <button className="small accent" onClick={() => rerender()} disabled={busy || (!prompt.trim() && !Object.keys(slots).length)} title={!prompt.trim() && !Object.keys(slots).length ? '提示词为空：先「从描述重铸槽位」或手动填写提示词' : ''}>🔁 重新渲染</button>
              <button className="small ghost" onClick={save} disabled={busy}>保存修改</button>
              <span className="ops-div" />
              <button className="small ghost" onClick={polish} disabled={busy || !versions.length} title="img2img denoise 0.12，构图与身份不变，仅补自然质感">✨ 微调 10%</button>
              <button className="small ghost" onClick={upscale} disabled={busy || !versions.length} title="像素级超分放大（写实 4xNomos / 动漫 4x-ESRGAN / 通用 RealESRGAN），构图身份不变，追加高清版本">🔍 超分放大</button>
              {asset._etype !== 'character' && <button className="small ghost" onClick={redrawFromRef} disabled={busy} title="粘贴网上找的真实物品/场景照片，img2img 重绘：结构、比例、屏幕与键帽文字保真，只换画风">📷 参考图重绘</button>}
              {isScene && <button className="small ghost" onClick={genIso} disabled={busy} title="生成 45° 等距空间布局全景图：俯瞰整个场景的结构与陈设排布，作为场景缩略图与锚点候选（镜头首帧 img2img 以此锁环境）">📐 布局图</button>}
              {!Object.keys(slots).length && <button className="small ghost" onClick={rebuild} disabled={busy} style={!prompt.trim() ? { background: 'var(--accent2)', color: '#fff', borderColor: 'var(--accent2)' } : undefined} title="本地 LLM 按方法论模板从描述反推结构化槽位；描述为占位文案时自动从剧本正文抽取该实体出场片段补上下文">🪄 从描述重铸槽位</button>}
            </div>
            {!prompt.trim() && !Object.keys(slots).length && (
              <div style={{ marginTop: 10, padding: '8px 10px', border: '1px solid var(--accent2)', borderRadius: 8, fontSize: 12, color: 'var(--text)' }}>
                ⚠ 提示词为空（拆解自动发现的候选）：直接渲染会被拦截。点上方 <b>🪄 从描述重铸槽位</b>，LLM 会自动从剧本正文抽取该角色出场片段反推外观设定。
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ---------- 导演台（对齐 RunningHub RHTV：按钮代替提示词碰运气） ---------- */
// 元数据只取一次（摄像机枚举 / 预设 / 风格库 / 人物调节），之后本地筛选
let __directorMeta = null
async function loadDirectorMeta() {
  if (!__directorMeta) __directorMeta = await get('/director/meta')
  return __directorMeta
}

// 风格卡片兜底底色：示例缩略图没生成/加载失败时，按 key 生成稳定渐变（不至于开天窗）
const styleTint = key => {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) % 360
  return `linear-gradient(135deg, hsl(${h} 42% 26%), hsl(${(h + 38) % 360} 46% 15%))`
}

function BtnRow({ title, hint, items, value, onPick, disabled }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 2 }}>
        <span style={{ fontSize: 12, color: 'var(--text-soft)', fontWeight: 600 }}>{title}</span>
        <span style={{ fontSize: 11, color: 'var(--dim)' }}>{hint}</span>
      </div>
      <div className="dir-btns">
        {items.map(it => (
          <button key={it.v === '' ? '_empty' : it.v} disabled={disabled}
            className={`dir-btn ${(value || '') === (it.v || '') ? 'on' : ''}`}
            title={it.hint || ''} onClick={() => onPick(it.v)}>
            {it.zh}{it.hint ? <em>{it.hint}</em> : null}
          </button>
        ))}
      </div>
    </div>
  )
}

function DirectorPanel({ shot, onClose, onApplied }) {
  const [meta, setMeta] = useState(null)
  const [s, setS] = useState(shot)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  useEffect(() => {
    loadDirectorMeta().then(setMeta).catch(e => setMsg('导演台数据加载失败：' + e.message))
  }, [])
  // 每次点按钮：写字段 → 后端立刻重算本集提示词（零 LLM，秒级），
  // 不然"点了按钮但出图不变"（出图只认 image_prompt）
  const apply = async (fields, note) => {
    setBusy(true)
    try {
      const r = await post(`/shots/${s.id}/director-apply`, { fields })
      setS(x => ({ ...x, ...fields }))
      setMsg(`✔ ${note}已写入（本集 ${r.reassembled} 镜提示词已重算）`)
      onApplied && onApplied()
    } catch (e) { setMsg('应用失败：' + e.message) }
    finally { setBusy(false) }
  }
  const usePreset = (p) => {
    const fields = {}
    for (const [k, v] of Object.entries(p)) {
      if (k === 'id' || k === 'zh' || k === 'desc') continue
      fields[k] = v
    }
    apply(fields, `预设「${p.zh}」`)
  }
  const cur = {
    shot_size: s.shot_size || '', camera_angle: s.camera_angle || '',
    camera_move: s.camera_move || '固定', camera_speed: s.camera_speed || 'normal',
    focal_length: s.focal_length || '', focus_transition: s.focus_transition || 'none',
    transition_in: s.transition_in || '',
  }
  const c = meta?.camera
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}
        style={{ width: 'min(900px, 94vw)', maxHeight: '88vh', overflow: 'auto' }}>
        <div className="modal-head">
          <div className="page-title">🎥 导演台 · 第 {s.idx} 镜</div>
          <button className="modal-x" onClick={onClose}>✕</button>
        </div>
        <div className="page-sub" style={{ marginTop: -4 }}>
          当前：{cur.shot_size} · {cur.camera_angle || '平视'} · {cur.camera_move}/{cur.camera_speed}
          {cur.focal_length ? ` · ${cur.focal_length}` : ''}{cur.focus_transition !== 'none' ? ` · ${cur.focus_transition}` : ''}
          ｜ 点按钮即写入镜头并重算提示词，不用再背运镜术语
        </div>
        {msg && <div className="card" style={{ borderColor: 'var(--ok)', margin: '8px 0', fontSize: 12 }}>{msg}</div>}
        {!c ? <div className="page-sub">加载中…</div> : (
          <>
            <div style={{ fontSize: 12, color: 'var(--accent-strong)', margin: '10px 0 6px', fontWeight: 600 }}>
              运镜预设（一键专业组合）
            </div>
            <div className="dir-presets">
              {(meta.presets || []).map(p => (
                <button key={p.id} className="dir-preset" disabled={busy} onClick={() => usePreset(p)}>
                  <b>{p.zh}</b>
                  <em>{p.desc}</em>
                  <span style={{ fontSize: 10, color: 'var(--dim)', display: 'block', marginTop: 3 }}>
                    {p.shot_size} · {p.camera_angle} · {p.camera_move}{p.camera_speed ? `/${p.camera_speed}` : ''}
                  </span>
                </button>
              ))}
            </div>
            <div style={{ height: 14 }} />
            <BtnRow title="景别" hint="主体占多大画面" items={c.shot_size} value={cur.shot_size}
              disabled={busy} onPick={v => apply({ shot_size: v }, `景别=${v}`)} />
            <BtnRow title="机位" hint="摄影机的高度与方向" items={c.angle} value={cur.camera_angle}
              disabled={busy} onPick={v => apply({ camera_angle: v }, `机位=${v}`)} />
            <BtnRow title="运镜" hint="镜头怎么动（位移型自动挂尾帧）" items={c.move} value={cur.camera_move}
              disabled={busy} onPick={v => {
                const it = c.move.find(x => x.v === v)
                apply({ camera_move: v, camera_dir: (it && it.dir) || '' }, `运镜=${v}`)
              }} />
            <BtnRow title="速度" hint="动得多快" items={c.speed} value={cur.camera_speed}
              disabled={busy} onPick={v => apply({ camera_speed: v }, `速度=${v}`)} />
            <BtnRow title="焦段" hint="决定空间压缩与透视" items={c.lens} value={cur.focal_length}
              disabled={busy} onPick={v => apply({ focal_length: v }, `焦段=${v || '不限'}`)} />
            <BtnRow title="焦点" hint="焦点放在谁身上" items={c.focus} value={cur.focus_transition}
              disabled={busy} onPick={v => apply({ focus_transition: v }, `焦点=${v}`)} />
            <BtnRow title="转场" hint="本镜从上一镜怎么进来" items={c.transition} value={cur.transition_in}
              disabled={busy} onPick={v => apply({ transition_in: v }, `转场=${v || '默认'}`)} />
            <div style={{ fontSize: 12, color: 'var(--accent-strong)', margin: '16px 0 6px', fontWeight: 600 }}>
              光影 / 色彩（滤镜层 · 纯提示词，不耗 token、不调云端）
            </div>
            {(meta.light_grade_groups || []).map(g => {
              const items = (meta.light_grades || []).filter(x => x.group === g)
              if (g === '光线') items.unshift({ v: '', zh: '跟随项目', hint: s.light_grade ? '清除单镜覆盖，回到全片预设' : '当前继承全片预设' })
              return <BtnRow key={g} title={g}
                hint={g === '光线' ? '轻一点/重一点、暖/冷、硬/柔' : '整体调色倾向（暗部与肤色的对撞）'}
                items={items} value={s.light_grade || ''} disabled={busy}
                onPick={v => apply({ light_grade: v }, `光影=${v ? (items.find(x => x.v === v) || {}).zh : '跟随项目'}`)} />
            })}
            <label style={{ fontSize: 11 }}>人物轨迹（可手改，位移时首帧/尾帧都会用）</label>
            <input defaultValue={s.character_path || ''}
              placeholder="如 from left edge walks to the counter then turns back to camera"
              onBlur={e => apply({ character_path: e.target.value }, '人物轨迹')}
              style={{ width: '100%', fontSize: 12 }} />
            <div style={{ height: 8 }} />
            <div className="row">
              <label style={{ fontSize: 11, color: 'var(--dim)' }}>
                <input type="checkbox" checked={!!s.needs_end_frame}
                  onChange={e => apply({ needs_end_frame: e.target.checked }, '尾帧')} /> 出尾帧（双帧 i2v 需要终点）
              </label>
            </div>
            <div style={{ marginTop: 10 }} className="ops-row">
              <button className="small ghost" onClick={onClose}>关闭</button>
              <span style={{ fontSize: 11, color: 'var(--dim)' }}>
                改完可用卡片上的「首帧 / 视频」重新生成，改动才落到画面上
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function StyleLibraryModal({ project, onClose, onApplied }) {
  const [lib, setLib] = useState(null)
  const [cat, setCat] = useState('全部')
  const [q, setQ] = useState('')
  const [cur, setCur] = useState(project.style_preset)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  useEffect(() => { loadDirectorMeta().then(m => setLib(m.styles)).catch(e => setMsg('风格库加载失败：' + e.message)) }, [])
  const use = async (key, label) => {
    setBusy(true)
    try {
      const r = await put(`/projects/${project.id}`, { style_preset: key })
      setCur(key)
      project.style_preset = key
      setMsg(`✔ 已套用「${label}」，${r.reassembled_prompts || 0} 个资产的提示词按新风格重组装（重新渲染即生效）`)
      onApplied && onApplied(key)
    } catch (e) { setMsg('套用失败：' + e.message) }
    finally { setBusy(false) }
  }
  if (!lib) return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head"><div className="page-title">🎨 风格库</div>
          <button className="modal-x" onClick={onClose}>✕</button></div>
        <div className="page-sub">{msg || '加载中…'}</div>
      </div>
    </div>
  )
  const items = lib.groups.flatMap(g => g.items.map(it => ({ ...it, category: g.name }))
    // 搜索时跨全部分类（否则停在某一类里搜别的类名永远 0 结果）
    .filter(it => q ? true : (cat === '全部' || it.category === cat)))
    .filter(it => !q || (it.label + it.key + it.category).toLowerCase().includes(q.toLowerCase()))
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}
        style={{ width: 'min(1000px, 95vw)', height: '84vh', display: 'flex', flexDirection: 'column' }}>
        <div className="modal-head">
          <div className="page-title">🎨 风格库 · {lib.total} 种
            {!!lib.hidden_total && (
              <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--dim)', marginLeft: 10 }}
                title={lib.hidden_note}>
                另有 {lib.hidden_total} 种暂不适用（像素/体素/设计示意类）
              </span>
            )}
          </div>
          <button className="modal-x" onClick={onClose}>✕</button>
        </div>
        <div className="row" style={{ marginBottom: 8 }}>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="搜索风格（国风 / 赛博 / 电影…）"
            style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: 'var(--dim)' }}>当前：{[...lib.groups.flatMap(g => g.items)].find(i => i.key === cur)?.label || cur}</span>
        </div>
        {msg && <div className="card" style={{ borderColor: 'var(--ok)', fontSize: 12, marginBottom: 8 }}>{msg}</div>}
        <div className="style-lib" style={{ flex: 1, minHeight: 0 }}>
          <div className="style-cats">
            {['全部', ...lib.groups.map(g => g.name)].map(n => (
              <button key={n} className={`style-cat ${cat === n ? 'on' : ''}`} onClick={() => setCat(n)}>
                {n}<span style={{ float: 'right', opacity: .6, fontSize: 10 }}>
                  {n === '全部' ? lib.total : lib.groups.find(g => g.name === n)?.items.length}
                </span>
              </button>
            ))}
          </div>
          <div className="style-grid">
            {items.map(it => (
              <div key={it.key} className={`style-card ${cur === it.key ? 'on' : ''}`}
                title={it.sample} onClick={() => !busy && use(it.key, it.label)}>
                <div className="style-thumb" style={{ background: styleTint(it.key) }}>
                  {it.thumb && <img src={it.thumb} alt="" loading="lazy"
                    onError={e => { e.currentTarget.style.display = 'none' }} />}
                  <span className="style-thumb-name">{it.label}</span>
                  {cur === it.key && <span className="style-thumb-cur">当前</span>}
                </div>
                <div style={{ padding: '6px 8px' }}>
                  <div style={{ fontSize: 11, color: 'var(--dim)' }}>
                    {[it.category, it.family].filter(Boolean).join(' · ')}
                  </div>
                </div>
              </div>
            ))}
            {!items.length && <div className="page-sub">没有匹配的风格</div>}
          </div>
        </div>
        <div style={{ fontSize: 11, color: 'var(--dim)', marginTop: 6 }}>
          套用后项目的风格锁整体切换（角色/场景/道具的提示词会按新锁重组装），已生成的旧图不动；要重新出图请回资产库点「重新渲染」。
        </div>
      </div>
    </div>
  )
}

/* 人物调节（对齐 RHTV「面部控制 / 姿态调整 / 形象设定 / 妆容调节」）：
   点 chip 直接替换对应槽位（再点一次取消），不重画整张图，改完重渲才生效 */
function CharacterAdjust({ slots, onChange }) {
  const [meta, setMeta] = useState(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { loadDirectorMeta().then(m => setMeta(m.character_adjust)).catch(() => {}) }, [])
  if (!meta) return null
  return (
    <div style={{ margin: '4px 0 8px' }}>
      <div className="row">
        <button className="small ghost" onClick={() => setOpen(o => !o)}
          title="按面部/表情/发型/妆容/体型/姿态/服装/饰物分区微调（只改这一项，不用重写整段提示词）">
          🧑 人物调节{open ? ' ▲' : ' ▼'}
        </button>
        <span style={{ fontSize: 11, color: 'var(--dim)' }}>点选即替换对应槽位，再点一次取消；改完点「重新渲染」</span>
      </div>
      {open && (
        <div style={{ marginTop: 6, border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px' }}>
          {meta.map(g => (
            <div key={g.slot} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11.5, color: 'var(--text-soft)', marginBottom: 4 }}>
                {g.zh}<span style={{ color: 'var(--dim)', marginLeft: 6 }}>{g.hint}</span>
              </div>
              <div className="mini-chips">
                {g.chips.map(c => (
                  <button key={c.en} className={`mini-chip ${(slots[g.slot] || '') === c.en ? 'on' : ''}`}
                    title={c.en}
                    onClick={() => onChange({ ...slots, [g.slot]: (slots[g.slot] || '') === c.en ? '' : c.en })}>
                    {c.zh}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ---------- P2 资产库 ---------- */
/* 道具"带文字"的前端预判：与后端 text_prop.looks_textual 同一套词表（双字以上，
   避免"签字笔/数字时钟"这类单字误判）。命中即卡片上提示「📝 带文字」。
   英文道具（双语项目）按整词匹配，跟后端 TEXT_PROP_WORDS_EN 保持一致。 */
const TEXT_PROP_WORDS = ['铭文', '刻字', '题字', '字迹', '字样', '带字', '有字',
  '匾额', '牌匾', '令牌', '腰牌', '木牌', '门牌', '招牌', '招贴', '符箓', '符纸', '符咒', '黄符', '灵符',
  '诏书', '圣旨', '榜文', '告示', '公文', '文书', '度牒', '通关文牒', '路引', '经卷', '经书', '秘籍', '功法卷',
  '卷轴', '手札', '书信', '密令', '遗嘱', '玉简', '竹简', '简牍', '木牍', '石刻',
  '契约', '地契', '房契', '契书', '账簿', '账册', '账本', '名录', '花名册', '票据', '兑换券', '银票', '票号',
  '印章', '官印', '玉玺', '印玺', '封条', '舆图', '地图', '阵图', '图谱', '碑刻', '石碑', '墓志',
  '牌位', '灵位', '谥册', '册封', '刻着', '刻有', '写着', '写有', '印着', '印有', '题着', '铭刻', '镌刻']
const TEXT_PROP_WORDS_EN = ['token', 'plaque', 'tablet', 'stele', 'sign', 'signboard', 'banner', 'poster',
  'certificate', 'decree', 'edict', 'warrant', 'manifest', 'contract', 'deed', 'scroll', 'manuscript',
  'grimoire', 'ledger', 'register', 'roster', 'ticket', 'voucher', 'coupon', 'passport', 'permit', 'badge',
  'talisman', 'charm', 'seal', 'stamp', 'label', 'notice', 'map', 'chart']
const TEXT_PROP_EXCLUDE = ['字典', '书桌', '书架', '文具', '签字笔', '标签纸', '印泥盒', '印刷机']
function looksTextualProp(name, extra) {
  let text = [name || '', extra || ''].join(' ')
  TEXT_PROP_EXCLUDE.forEach(w => { text = text.split(w).join('') })
  if (TEXT_PROP_WORDS.some(w => text.includes(w))) return true
  const words = new Set((text.toLowerCase().match(/[a-z]+/g) || []))
  return TEXT_PROP_WORDS_EN.some(w => words.has(w))
}

/* ---------- 图片文字局部微调（框选重绘，只动框内） ---------- */
// 与"整图重渲"的区别：这里在**同一张已生成的图**上，只把文字框内部重新采样。
// 框外的纸纹、折痕、朱印、边框、光影全部沿用原图 latent（SetLatentNoiseMask）。
/* 三类资产的默认文字框（归一化）：文字最常出现的位置 */
const TEXT_BOX_BY_ETYPE = {
  prop: { x: 0.335, y: 0.195, w: 0.30, h: 0.545 },       // 牌面/券面竖排主体区
  scene: { x: 0.26, y: 0.22, w: 0.48, h: 0.26 },          // 门额/牌匾/招牌横块
  character: { x: 0.04, y: 0.86, w: 0.92, h: 0.11 },      // 设计图底部标注/信息行
}

function TextEditModal({ assetId, name, etype, onClose, onSubmitted }) {
  const [text, setText] = useState(name || '')
  const [box, setBox] = useState({ ...(TEXT_BOX_BY_ETYPE[etype] || TEXT_BOX_BY_ETYPE.prop) })
  const [denoise, setDenoise] = useState(0.88)
  const [autoLoop, setAutoLoop] = useState(true)
  const [maxRounds, setMaxRounds] = useState(3)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const drag = useRef(null)
  const stage = useRef(null)
  const pt = (e, r) => ({
    x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
    y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
  })
  const down = e => {
    if (!stage.current) return
    e.preventDefault()
    drag.current = { a: pt(e, stage.current.getBoundingClientRect()), r: stage.current.getBoundingClientRect() }
  }
  const move = e => {
    const d = drag.current
    if (!d) return
    const b = pt(e, d.r)
    const x = Math.min(d.a.x, b.x), y = Math.min(d.a.y, b.y)
    const w = Math.abs(b.x - d.a.x), h = Math.abs(b.y - d.a.y)
    if (w > 0.02 && h > 0.02) setBox({ x, y, w, h })
  }
  const up = () => { drag.current = null }
  const submit = async () => {
    if (!text.trim()) { setMsg('先填要写的文字'); return }
    setBusy(true)
    try {
      const r = await post(`/assets/${assetId}/text-edit`, {
        text: text.trim(), box, denoise,
        auto_loop: autoLoop, max_rounds: autoLoop ? maxRounds : 1,
      })
      setMsg(autoLoop
        ? `✔ 任务 #${r.task_id} 已入队：自动迭代最多 ${maxRounds} 轮——每轮画完用本地 OCR 读框内的字，读不清就缩框重画（面积压到上一轮 85% 以内），直到读对。只动琥珀框内，框外一点不动。约 1–4 分钟，完成后点资产页「刷新」`
        : `✔ 任务 #${r.task_id} 已入队：只重画琥珀框内，框外一点不动（本地 Qwen-Image，零 token、零云端）。约 1–2 分钟，完成后点资产页「刷新」`)
      onSubmitted && onSubmitted()
    } catch (e) { setMsg('提交失败：' + e.message) }
    finally { setBusy(false) }
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}
        style={{ width: 'min(760px, 94vw)', maxHeight: '92vh', overflow: 'auto' }}>
        <div className="modal-head">
          <div className="page-title">📝 局部改字 · {name}</div>
          <button className="modal-x" onClick={onClose}>✕</button>
        </div>
        <div className="page-sub" style={{ marginTop: -4 }}>
          在图上按住拖动框住文字区域（琥珀框＝会重画的区域）；框外纸纹/折痕/朱印/光影一律保留。
          {etype === 'scene' && '场景设计图：框住门额 / 牌匾 / 招牌上的字。'}
          {etype === 'character' && '角色设计图：框住面板旁的手写标注或信息行，别框到立绘和脸。'}
          {etype === 'prop' && '道具设计图：框住牌面 / 券面 / 铭文本身。'}
        </div>
        {msg && <div className="card" style={{ borderColor: 'var(--ok)', margin: '8px 0', fontSize: 12 }}>{msg}</div>}
        <div ref={stage} onMouseDown={down} onMouseMove={move} onMouseUp={up} onMouseLeave={up}
          style={{ position: 'relative', userSelect: 'none', cursor: 'crosshair', marginTop: 8, lineHeight: 0 }}>
          <img src={`${API}/assets/${assetId}/file`} draggable={false}
            style={{ width: '100%', display: 'block', borderRadius: 6 }} />
          <div style={{
            position: 'absolute', left: `${box.x * 100}%`, top: `${box.y * 100}%`,
            width: `${box.w * 100}%`, height: `${box.h * 100}%`,
            border: '2px solid #f5a623', boxShadow: '0 0 0 9999px rgba(0,0,0,.22)',
            pointerEvents: 'none', borderRadius: 2,
          }} />
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <label style={{ fontSize: 12, minWidth: 84 }}>要写的字</label>
          <input value={text} onChange={e => setText(e.target.value)} maxLength={24}
            placeholder="中文如 青云宗令牌，英文如 QING YUN SECT" style={{ flex: 1 }} />
          <button className="small ghost" onClick={() => setBox({ ...(TEXT_BOX_BY_ETYPE[etype] || TEXT_BOX_BY_ETYPE.prop) })}
            title="回到该类资产的默认文字区">重置框</button>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <label style={{ fontSize: 12, minWidth: 84 }}>重绘强度</label>
          <input type="range" min={0.6} max={0.98} step={0.02} value={denoise}
            onChange={e => setDenoise(Number(e.target.value))} style={{ flex: 1 }} />
          <span style={{ fontSize: 12, color: 'var(--dim)', width: 44 }}>{denoise.toFixed(2)}</span>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <label style={{ fontSize: 12, minWidth: 84, display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
            <input type="checkbox" checked={autoLoop} onChange={e => setAutoLoop(e.target.checked)}
              style={{ width: 'auto', minWidth: 0 }} />
            自动迭代判字
          </label>
          <span style={{ fontSize: 11, color: 'var(--dim)', flex: 1, lineHeight: 1.5 }}>
            每轮画完本地 OCR 读一遍框内字，读不清/乱码就缩框重画，直到读对
          </span>
          <select value={maxRounds} disabled={!autoLoop} onChange={e => setMaxRounds(Number(e.target.value))}
            style={{ width: 100 }}>
            {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>最多 {n} 轮</option>)}
          </select>
        </div>
        <div className="page-sub" style={{ fontSize: 11, marginTop: 4 }}>
          框要贴住字本身：框压到朱印/边框会把它们一起重画变淡；字写糊/笔画不清就把强度往 0.95 拉；
          字没错只是想更清楚，可以把强度降到 0.7 左右只做重绘锐化。
          中文按毛笔/印刷体重写，英文按印刷大写字母重写（本地 Qwen-Image，中英文同一个通道）。
          自动迭代时：第 1 轮用你框的范围，之后每轮只框"目标字所在的那一块"并压到上一轮 85% 以内，
          重绘强度每轮 +0.03；OCR 连着两轮读不出字（强光/极小字/笔迹太草）会自动停，不白跑。
        </div>
        <div className="ops-row" style={{ marginTop: 10 }}>
          <button className="small" disabled={busy} onClick={submit}>{busy ? '提交中…' : '开始局部重绘'}</button>
          <button className="small ghost" onClick={onClose}>关闭</button>
          <span style={{ fontSize: 11, color: 'var(--dim)' }}>
            产物作为新版本追加，原图保留可回退
          </span>
        </div>
      </div>
    </div>
  )
}

function AssetsPage({ project, refreshTasks, setStage }) {
  const [data, setData] = useState(null)
  const [models, setModels] = useState([])
  const [editing, setEditing] = useState(null)
  const [notice, setNotice] = useState('')
  const [stash, setStash] = useState([])
  const [stashIds, setStashIds] = useState({})
  const [stashBusy, setStashBusy] = useState(false)
  const [styleLib, setStyleLib] = useState(false)
  const [textEdit, setTextEdit] = useState(null)   // 正在「📝 改字」的道具（含最新 image_id）

  const load = () => api(`/projects/${project.id}/assets`).then(setData)
  const loadStash = () => api(`/projects/${project.id}/stash`).then(setStash).catch(() => {})
  useEffect(() => { load() }, [project.id, project._assetsVersion])
  useEffect(() => { loadStash() }, [project.id])
  useEffect(() => { api('/system').then(s => setModels(Object.entries(s.models).map(([key, v]) => ({ key, ...v })))) }, [])
  if (!data) return <div className="page-sub">加载中…</div>
  const img = id => `${API}/assets/${id}/file`

  // 卡片上的「📝 改字」：在**最新一张图**上框选文字区局部重绘（不重画整图、不耗 token）
  // 2026-11-28 起三类资产都有文字：道具设计图牌面 / 场景设计图门额 / 角色设计图标注
  const openTextEdit = (a, etype) => {
    if (!a.image_ids || !a.image_ids.length) {
      setNotice(`「${a.name}」还没有图：先渲染一张，再来局部改字`)
      return
    }
    setTextEdit({ asset: a, etype, imageId: a.image_ids[a.image_ids.length - 1] })
  }

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

  const autoAnchors = async () => {
    try {
      const r = await post(`/projects/${project.id}/auto-scene-anchors`, {})
      setNotice(`场景锚图任务 #${r.task_id} 已入队：无锚场景自动生成 45° iso 布局全景图并设为锚点（已有锚图跳过），完成后分镜首帧自动注入锁环境一致性`)
      refreshTasks()
    } catch (e) { setNotice(`发起失败：${e.message}`) }
  }

  const wall = (list, etype, landscape) => (
    <>
      <div className="section-head">
        <h3>{ENTITY_LABEL[etype]}<em>（{list.length}）</em></h3>
        <span className="section-hint">点击卡片可编辑提示词 / 换模型 / 重新渲染</span>
        {etype === 'scene' &&
          <button className="small ghost" style={{ marginLeft: 'auto' }} title="无锚场景自动生成 45° iso 等距剖面布局全景图并设为锚点（缩略图法）：分镜首帧注入此图锁定环境布局一致性；已有锚图的场景跳过"
            onClick={autoAnchors}>⚓ 补齐场景锚图</button>}
      </div>
      <div className="grid">
        {list.map(a => (
          <div key={a.id} className={`asset-card ${etype === 'character' ? 'character-sheet' : ''} ${landscape ? 'landscape' : ''}`} style={{ cursor: 'pointer' }}
            onClick={() => setEditing({ ...a, _etype: etype, project_id: project.id })}>
            <div className="card-media">
              {a.image_ids.length
                ? <img src={img(a.image_ids[a.image_ids.length - 1])} />
                : <div className="media-empty">未生成 · 点击配置{etype === 'character' && !a.has_prompt ? '（先补全槽位）' : ''}</div>}
              <button className="asset-del" title="删除资产（含全部生成图，不可恢复）"
                onClick={e => { e.stopPropagation(); deleteAsset(etype, a) }}>删除</button>
              {a.image_ids.length > 0 &&
                <button className="small" title={etype === 'scene'
                  ? '在最新一张场景设计图上框住门额/牌匾/招牌文字局部重绘：框外墙面/光影不动，不耗 token、不调云端'
                  : etype === 'character'
                    ? '在最新一张角色设计图上框住面板旁的手写标注/信息行局部重绘：框外立绘与版式不动，不耗 token'
                    : '在最新一张道具设计图上框住牌面/券面文字局部重绘：框外纸纹/朱印/光影不动，不耗 token、不调云端'}
                  style={{ position: 'absolute', bottom: 8, right: 8, background: 'rgba(245,166,35,.92)', borderColor: '#f5a623', color: '#1a1a1a', fontWeight: 600 }}
                  onClick={e => { e.stopPropagation(); openTextEdit(a, etype) }}>📝 改字</button>}
            </div>
            <div className="info">
              <div className="name-row">
                <span className="name">{a.name}</span>
                {etype === 'prop' && looksTextualProp(a.name, a.description) &&
                  <span className="tag" title="文字是画面主体 → 生成自动分流：中文走 MOSS-Image、英文走 Ideogram 4（全本地）；错字用「📝 改字」局部重绘（英文档需整图重出）">📝 带文字</span>}
                {a.render_count > 0 && <span className="tag">渲染 {a.render_count} 次</span>}
                {a.image_ids.length > 1 && <span className="tag" title="含微调/超分等衍生图">{a.image_ids.length} 图</span>}
              </div>
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
      <div className="page-sub">角色 / 场景 / 道具统一出<b>设计图</b>（对齐 RunningHub 无限画布 RHTV 的概念设定板）：改提示词、选模型档位、重新渲染追加新版本；图上的字用「📝 改字」框选局部重写</div>
      <div className="row" style={{ margin: '8px 0 12px' }}>
        <button className="small ghost" onClick={() => setStyleLib(true)}
          title="对齐 RunningHub RHTV 的风格库：分类 + 搜索 + 缩略卡片，点卡片整体切换全片画风">🎨 风格库</button>
        <span className="page-sub" style={{ fontSize: 11 }}>当前：{project.style_preset}｜切完风格请按方案重渲，旧图不会自己变</span>
      </div>
      {notice && <div className="card" style={{ borderColor: 'var(--ok)' }}>{notice}</div>}
      {stashCard}
      {wall(data.characters, 'character')}
      {wall(data.scenes, 'scene', true)}
      {wall(data.props, 'prop')}
      {editing && <AssetEditor asset={editing} models={models} refreshTasks={refreshTasks}
        onDeleted={load}
        onTextEdit={a => { const et = editing._etype; setEditing(null); openTextEdit(a, et) }}
        onClose={(reload, note) => { setEditing(null); if (reload) load(); if (note) setNotice(note) }} />}
      {textEdit && <TextEditModal assetId={textEdit.imageId} name={textEdit.asset.name} etype={textEdit.etype}
        onClose={() => setTextEdit(null)}
        onSubmitted={() => { setNotice(`「${textEdit.asset.name}」局部改字任务已入队：只重画框内文字，框外不动。约 1-2 分钟，完成后点「刷新」看新版本`); refreshTasks && refreshTasks() }} />}
      {styleLib && <StyleLibraryModal project={project} onClose={() => setStyleLib(false)}
        onApplied={() => load()} />}
      <WizardBar stage="assets" setStage={setStage || (() => {})} nextLabel="下一步：分镜镜头卡 →" />
    </div>
  )
}

/* ---------- 底部任务栏 ---------- */
const STATUS_LABEL = { running: '推理中', pending: '排队中', paused: '已暂停', done: '完成', failed: '失败', cancelled: '已取消', interrupted: '已中断' }
// 技术异常 → 一句人话：面板上的 ✗ 行不再甩 httpx traceback 首行
const ERR_HINTS = [
  ['All connection attempts failed', 'ComfyUI 不可达（127.0.0.1:8188 无响应）'],
  ['轮询偶发挂起', 'ComfyUI 轮询挂起（服务端已算完）'],
  ['进程重启中断', '服务重启打断'],
  ['机器离线', '机器离线打断'],
  ['环境离线', '环境离线打断'],
]
function errLine(t) {
  if (t.status === 'interrupted') return '已中断，点「继续」按原参数重跑'
  const all = t.error || ''
  const hit = ERR_HINTS.find(([k]) => all.includes(k))
  return hit ? hit[1] : all.split('\n')[0]
}
// 已跑时长：H3 在 8G 上单条 10-30 分钟、进度长期停在 0.3，
// 不显示 elapsed 时用户只能判断成"卡死了"，这是"任务停住"体感的一半
function elapsedLabel(s) {
  if (!s) return ''
  const ms = Date.now() - new Date(String(s).replace(' ', 'T')).getTime()
  if (!isFinite(ms) || ms < 0) return ''
  const m = Math.floor(ms / 60000)
  return m < 1 ? '刚开始' : `已跑 ${m} 分`
}
function TaskBar({ tasks, vram, refreshTasks }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(null)
  const active = tasks.filter(t => t.status === 'running' || t.status === 'pending')
  const shown = active.length ? active : tasks.slice(0, 2)
  const act = async (tid, action) => {
    setBusy(tid)
    try { await post(`/tasks/${tid}/${action}`) }
    catch (e) { alert(String(e.message || e).slice(0, 200)) }
    await refreshTasks()
    setBusy(null)
  }
  // 每种状态可用的控制按钮
  const ctl = t => {
    if (t.status === 'running') return [['取消', 'cancel']]
    if (t.status === 'pending') return [['暂停', 'pause'], ['取消', 'cancel']]
    if (t.status === 'paused') return [['继续', 'resume'], ['取消', 'cancel']]
    if (t.status === 'interrupted') return [['继续', 'retry']]
    if (t.status === 'failed') return [['重试', 'retry']]
    return []
  }
  // 详情面板只留「进行中的」+ 最近 5 条终态：此前塞最近 15 条，
  // 服务重启/服务中断留下的失败行会一直堆在列表里看不到当前进度。
  const detail = [
    ...tasks.filter(t => ['running', 'pending', 'paused'].includes(t.status)),
    ...tasks.filter(t => !['running', 'pending', 'paused'].includes(t.status)).slice(0, 5),
  ]
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
      <button className="ghost" style={{ marginLeft: 'auto', fontSize: 12, padding: '3px 12px', borderRadius: 8, cursor: 'pointer' }}
              onClick={() => setOpen(o => !o)}>
        {open ? '收起队列 ▾' : `队列详情 ▴ (${tasks.length})`}
      </button>
      {open && (
        <div className="task-detail-panel">
          <div className="task-detail-head">任务详情（进行中 {active.length} 条 + 最近 5 条终态 · 排队中可暂停，推理中只能取消）</div>
          {detail.map(t => (
            <div key={t.id} className="task-detail-row">
              <span className="task-id">#{t.id}</span>
              <span className={`badge ${t.status}`}>{STATUS_LABEL[t.status] || t.status}</span>
              <span className="task-desc" title={t.error || ''}>{t.desc || t.type}</span>
              <div className="progress-track" style={{ flex: 1, minWidth: 80 }}>
                <div className="progress-fill" style={{ width: `${Math.round((t.progress || 0) * 100)}%` }} />
              </div>
              <span className="task-pct">{Math.round((t.progress || 0) * 100)}%</span>
              {['running', 'paused'].includes(t.status) && t.started_at && (
                <span style={{ color: 'var(--dim)', fontSize: 11, whiteSpace: 'nowrap' }}>{elapsedLabel(t.started_at)}</span>
              )}
              <span className="task-stage" title={t.error || t.stage}>
                {t.error ? '✗ ' + errLine(t) : (t.stage || '')}
              </span>
              {ctl(t).map(([label, action]) => (
                <button key={action} className="ghost" style={{ fontSize: 12, padding: '2px 10px', borderRadius: 8, cursor: 'pointer' }}
                        disabled={busy === t.id}
                        onClick={() => act(t.id, action)}>{label}</button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ---------- 后台配置面板（模型 / LoRA / 加速 / 服务地址） ---------- */
function CfgField({ label, hint, children }) {
  return (
    <div className="cfg-field">
      <div className="cfg-label">{label}{hint && <span className="cfg-hint">{hint}</span>}</div>
      {children}
    </div>
  )
}

function ModelSelect({ value, onChange, options, emptyText }) {
  const known = (options || []).some(o => o.key === value)
  return (
    <select className="cfg-select" value={value || ''} onChange={e => onChange(e.target.value)}>
      {!known && <option value={value || ''}>{value ? `${value}（不在注册表）` : (emptyText || '未选择')}</option>}
      {(options || []).map(o => (
        <option key={o.key} value={o.key}>{o.label} · {o.family} · {o.vram_gb}G/{o.tier}</option>
      ))}
    </select>
  )
}

function SettingsModal({ open, onClose }) {
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState('')
  // 选项卡：模型档 / LoRA 与加速 / 服务与路径 / 音色源（本地）
  const [tab, setTab] = useState('models')
  const [vs, setVs] = useState(null)            // GET /voice-sources 快照
  const [vsDraft, setVsDraft] = useState(null)  // 本地音色源连接参数草稿
  const [vsMsg, setVsMsg] = useState('')
  const [vsBusy, setVsBusy] = useState('')
  const [probe, setProbe] = useState(null)
  const [newVoice, setNewVoice] = useState({ group: '本地音色', label: '', voice: '', gender: 'f' })
  const [confirmDel, setConfirmDel] = useState('')   // 两段式删除：第一次点亮，3s 内再点才真删
  // 本地音色库（积木音色库 1248 款参考音频）：分页浏览 + 原声试听 + 加入配音清单
  const [lib, setLib] = useState(null)
  const [libQ, setLibQ] = useState('')
  const [libGender, setLibGender] = useState('')
  const [libCat, setLibCat] = useState('')
  const [libBusy, setLibBusy] = useState('')
  const [libMsg, setLibMsg] = useState('')
  const load = () => api('/settings').then(d => {
    setData(d); setDraft(JSON.parse(JSON.stringify(d.config)))
  }).catch(e => setMsg('读取配置失败：' + e.message))
  const loadVs = () => api('/voice-sources').then(d => {
    setVs(d)
    setVsDraft({
      provider: d.provider || 'edge',
      url: (d.local && d.local.url) || '',
      api: (d.local && d.local.api) || 'gpt-sovits',
      timeout: (d.local && d.local.timeout) || 60,
    })
  }).catch(e => setVsMsg('读取音色源失败：' + e.message))
  useEffect(() => {
    if (!open) return
    setMsg(''); setVsMsg(''); setProbe(null); setLib(null); setLibMsg('')
    load(); loadVs(); loadLib(1, '', '', '')
  }, [open])
  if (!open) return null
  const saveVsSource = async () => {
    if (!vsDraft) return
    setVsBusy('save')
    try {
      const r = await put('/voice-sources', {
        provider: vsDraft.provider, local_url: vsDraft.url,
        local_api: vsDraft.api, local_timeout: Number(vsDraft.timeout) || 60,
      })
      setVs(r)
      setVsMsg(vsDraft.provider === 'local_http'
        ? '已写入 data/voice_sources.yaml。本地音色（provider=local）现在走自建服务，内置 edge 音色不受影响。'
        : '已写入 data/voice_sources.yaml。全局音色源为 edge-tts 在线接口。')
    } catch (e) { setVsMsg('保存失败：' + e.message) } finally { setVsBusy('') }
  }
  const probeVs = async () => {
    if (!vsDraft) return
    setVsBusy('probe'); setProbe(null)
    try {
      const r = await post('/voice-sources/probe', { url: vsDraft.url, api: vsDraft.api })
      setProbe(r)
    } catch (e) { setProbe({ ok: false, error: e.message }) } finally { setVsBusy('') }
  }
  const addVsItem = async () => {
    setVsBusy('add')
    try {
      const r = await post('/voice-sources/items', newVoice)
      setVs(r); setVsMsg(`已添加音色「${newVoice.label}」，配音页下拉里会出现（分组：${newVoice.group}）。`)
      setNewVoice(n => ({ ...n, label: '', voice: '' }))
    } catch (e) { setVsMsg('添加失败：' + e.message) } finally { setVsBusy('') }
  }
  const delVsItem = async (key, label) => {
    // 两段式：第一次点只点亮确认态（原生 confirm 会阻塞页面，自动化也卡死），3 秒内再点才真删
    if (confirmDel !== key) {
      setConfirmDel(key)
      setTimeout(() => setConfirmDel(c => (c === key ? '' : c)), 3000)
      return
    }
    setConfirmDel('')
    setVsBusy('del')
    try {
      const r = await del('/voice-sources/items/' + encodeURIComponent(key))
      setVs(r); setVsMsg(`已删除音色「${label}」。已分配它的角色会回到未分配，去配音页重新选。`)
    } catch (e) { setVsMsg('删除失败：' + e.message) } finally { setVsBusy('') }
  }
  const loadLib = (page = 1, q = libQ, g = libGender, c = libCat) => {
    setLibBusy('load')
    api(`/voice-library?q=${encodeURIComponent(q)}&gender=${encodeURIComponent(g)}` +
        `&category=${encodeURIComponent(c)}&page=${page}&size=20`)
      .then(d => setLib(d))
      .catch(e => setLibMsg('读取音色库失败：' + e.message))
      .finally(() => setLibBusy(''))
  }
  const addLibItem = async (code, name) => {
    setLibBusy('add:' + code)
    try {
      const r = await post(`/voice-library/${encodeURIComponent(code)}/add`, {})
      setVs(r); setLibMsg(`已把「${name}（${code}）」加入配音清单（来源：本地音色库）。`)
    } catch (e) { setLibMsg('加入失败：' + e.message) } finally { setLibBusy('') }
  }
  const addLibBatch = async () => {
    if (!lib || !lib.items.length) return
    setLibBusy('batch')
    try {
      const r = await post('/voice-library/add-batch', { codes: lib.items.map(i => i.code) })
      if (r.state) setVs(r.state)
      setLibMsg(`本页加入：新增 ${r.added} 条，已有 ${r.skipped} 条` +
        (r.failed && r.failed.length ? `，失败 ${r.failed.length} 条（${r.failed[0]}）` : '') + '。')
    } catch (e) { setLibMsg('批量加入失败：' + e.message) } finally { setLibBusy('') }
  }
  const previewVoice = (voice) => {
    new Audio(`/api/voice-preview-file?voice=${encodeURIComponent(voice)}&pid=1&ts=${Date.now()}`).play()
  }
  const set = (g, k, v) => setDraft(d => ({ ...d, [g]: { ...((d || {})[g] || {}), [k]: v } }))
  const cfg = draft || {}
  const opts = (data && data.options) || {}
  const save = async () => {
    // 只提交真正改过的键：整份 config 回传时，后端按"哪些键变了"判要不要重启，
    // 全量提交会让"只改了个下拉"也提示重启后端。这条 diff 让提示与事实一致。
    const base = (data && data.config) || {}
    const patch = {}
    Object.keys(cfg).forEach(g => {
      const cur = cfg[g] || {}, old = base[g] || {}
      const ch = {}
      Object.keys(cur).forEach(k => { if (String(cur[k]) !== String(old[k])) ch[k] = cur[k] })
      if (Object.keys(ch).length) patch[g] = ch
    })
    if (!Object.keys(patch).length) { setMsg('没有改动。'); return }
    setBusy('save')
    try {
      const r = await put('/settings', patch)
      setData(d => ({ ...d, config: r.config, effective: { ...(d.effective || {}), models: r.config.models } }))
      setDraft(JSON.parse(JSON.stringify(r.config)))
      await load()
      setMsg(r.need_restart && r.need_restart.length
        ? `已保存到 data/settings.yaml。需要重启：${r.need_restart.join('、')} 才生效。`
        : '已保存到 data/settings.yaml，即时生效（下一次生成任务按新配置选模）。')
    } catch (e) { setMsg('保存失败：' + e.message) } finally { setBusy('') }
  }
  const restartComfy = async () => {
    setBusy('comfy')
    try {
      const r = await post('/settings/restart-comfy', {})
      setMsg(r.ok ? '已按新参数重启 ComfyUI，冷启动约 7-14 分钟（这段时间生成任务会等待）。'
        : '重启失败，看后端日志。')
    } catch (e) { setMsg('重启被拒或失败：' + e.message) } finally { setBusy('') }
  }
  return (
    <div className="cfg-overlay" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="cfg-modal">
        <div className="cfg-head">
          <div>
            <div className="cfg-title">后台配置</div>
            <div className="cfg-sub">模型档位、参考链路、LoRA 与加速、服务地址、音色源；前四项写进 backend/data/settings.yaml，音色源写进 backend/data/voice_sources.yaml</div>
          </div>
          <button className="cfg-x" onClick={onClose} title="关闭">✕</button>
        </div>

        {!data && <div className="cfg-note">正在读取配置…</div>}

        {data && <>
          <div className="cfg-tabs">
            {[['models', '模型档位'], ['lora', 'LoRA 与加速'], ['server', '服务与路径'], ['tts', '音色源（本地）']]
              .map(([k, l]) => (
                <button key={k} className={'cfg-tab' + (tab === k ? ' on' : '')}
                  onClick={() => setTab(k)}>{l}</button>
              ))}
          </div>
          <div className="cfg-body" data-tab={tab}>
            <div className="cfg-group" data-tab="models">
              <div className="cfg-group-title">模型选择</div>
              <div className="cfg-grid">
                <CfgField label="生图模型" hint="定妆照 / 场景 / 道具 / 修图 主链路">
                  <ModelSelect value={cfg.models?.default_image} options={opts.image}
                    onChange={v => set('models', 'default_image', v)} />
                </CfgField>
                <CfgField label="生视频模型" hint="分镜主链路默认档（单镜/批量/重链都跟它）">
                  <ModelSelect value={cfg.models?.default_video} options={opts.video}
                    onChange={v => set('models', 'default_video', v)} />
                </CfgField>
                <CfgField label="参考生图 · 写实/3D 族" hint="首帧 IPAdapter 锁脸底模，只能 SDXL 族">
                  <ModelSelect value={cfg.models?.ref_image_photo} options={opts.ref_image}
                    onChange={v => set('models', 'ref_image_photo', v)} />
                </CfgField>
                <CfgField label="参考生图 · 动漫/手绘族" hint="动漫族首帧与九宫格底模">
                  <ModelSelect value={cfg.models?.ref_image_anime} options={opts.ref_image}
                    onChange={v => set('models', 'ref_image_anime', v)} />
                </CfgField>
                <CfgField label="参考生视频 · 转场/首尾帧" hint="双帧约束（转场镜、向后重链）：H3 turbo 带原生音频，Wan2.2 首尾帧 Q4 双模型 4 步更省显存">
                  <ModelSelect value={cfg.models?.ref_video} options={opts.ref_video}
                    onChange={v => set('models', 'ref_video', v)} />
                </CfgField>
                <CfgField label="口型模型" hint="说话镜音频驱动">
                  <ModelSelect value={cfg.models?.talk_video} options={opts.talk}
                    onChange={v => set('models', 'talk_video', v)} />
                </CfgField>
              </div>
              <div className="cfg-tip">选档即时生效；参考链路只接受有对应工作流模板的档，选错会在任务里报错。</div>
            </div>

            <div className="cfg-group" data-tab="lora">
              <div className="cfg-group-title">LoRA 与加速</div>
              <div className="cfg-grid">
                <CfgField label="LoRA 根目录" hint={`扫描到 ${(data.loras || []).length} 个文件`}>
                  <input className="cfg-input" value={cfg.lora?.dir || ''}
                    onChange={e => set('lora', 'dir', e.target.value)} />
                </CfgField>
                <CfgField label="步数蒸馏 LoRA" hint="WAN 4 步加速用哪一个">
                  <select className="cfg-select" value={cfg.lora?.video_step_lora || ''}
                    onChange={e => set('lora', 'video_step_lora', e.target.value)}>
                    {!(data.loras || []).some(l => l.name === cfg.lora?.video_step_lora) &&
                      <option value={cfg.lora?.video_step_lora || ''}>{cfg.lora?.video_step_lora || '未选择'}</option>}
                    {(data.loras || []).map(l => (
                      <option key={l.name} value={l.name}>{l.name}（{l.size_gb}G）</option>
                    ))}
                  </select>
                </CfgField>
                <CfgField label="启用步数蒸馏" hint="关掉会把采样步数抬到下方值，慢但画质更足">
                  <div className="cfg-switch-row">
                    <label className="cfg-switch">
                      <input type="checkbox" checked={!!cfg.lora?.enable_video_step_lora}
                        onChange={e => set('lora', 'enable_video_step_lora', e.target.checked)} />
                      <span>{cfg.lora?.enable_video_step_lora ? '已启用（4 步采样）' : '已关闭（按采样步数走）'}</span>
                    </label>
                  </div>
                </CfgField>
                <CfgField label="关闭蒸馏后的采样步数" hint="建议 16-24">
                  <input className="cfg-input" type="number" min="4" max="60"
                    value={cfg.accel?.video_steps ?? 20}
                    onChange={e => set('accel', 'video_steps', Number(e.target.value))} />
                </CfgField>
                <CfgField label="注意力后端（加速方法）" hint="sage 需已装 sageattention；改完要重启 ComfyUI">
                  <select className="cfg-select" value={cfg.accel?.attention || 'pytorch'}
                    onChange={e => set('accel', 'attention', e.target.value)}>
                    <option value="pytorch">PyTorch SD attentention（默认·最稳）</option>
                    <option value="sage">SageAttention（更快·8G 卡收益明显）</option>
                  </select>
                </CfgField>
              </div>
              <div className="cfg-tip">WAN 的 fp8 + blockswap 已写在工作流模板里，属于固定加速；面板这里管的是"要不要挂蒸馏 LoRA"和 ComfyUI 的注意力实现。</div>
            </div>

            <div className="cfg-group" data-tab="server">
              <div className="cfg-group-title">服务与路径 <span className="cfg-badge">重启后端生效</span></div>
              <div className="cfg-grid">
                <CfgField label="ComfyUI 地址">
                  <input className="cfg-input" value={cfg.server?.comfyui_url || ''}
                    onChange={e => set('server', 'comfyui_url', e.target.value)} />
                </CfgField>
                <CfgField label="ComfyUI 安装目录">
                  <input className="cfg-input" value={cfg.server?.comfyui_dir || ''}
                    onChange={e => set('server', 'comfyui_dir', e.target.value)} />
                </CfgField>
                <CfgField label="extra_model_paths.yaml">
                  <input className="cfg-input" value={cfg.server?.extra_model_paths || ''}
                    onChange={e => set('server', 'extra_model_paths', e.target.value)} />
                </CfgField>
                <CfgField label="Ollama 地址">
                  <input className="cfg-input" value={cfg.server?.ollama_url || ''}
                    onChange={e => set('server', 'ollama_url', e.target.value)} />
                </CfgField>
                <CfgField label="Ollama 模型" hint="剧本 / 拆解 / 续写用的本地 LLM">
                  {(data.ollama_models || []).length
                    ? <select className="cfg-select" value={cfg.server?.ollama_model || ''}
                        onChange={e => set('server', 'ollama_model', e.target.value)}>
                        {!(data.ollama_models || []).includes(cfg.server?.ollama_model) &&
                          <option value={cfg.server?.ollama_model || ''}>{cfg.server?.ollama_model || '未选择'}</option>}
                        {data.ollama_models.map(m => <option key={m} value={m}>{m}</option>)}
                      </select>
                    : <input className="cfg-input" value={cfg.server?.ollama_model || ''}
                        onChange={e => set('server', 'ollama_model', e.target.value)} />}
                </CfgField>
              </div>
            </div>

            {vs && <>
              <div className="cfg-group" data-tab="tts">
                <div className="cfg-group-title">音色源
                  <span className={'cfg-badge' + (vsDraft?.provider === 'local_http' ? ' warn' : '')}>
                    当前：{vsDraft?.provider === 'local_http' ? '本地 HTTP 服务' : 'edge-tts 在线'}
                  </span>
                </div>
                <div className="cfg-grid">
                  <CfgField label="音色源类型" hint="edge = 内置 14 个在线音色；本地 = 自建 TTS 服务">
                    <select className="cfg-select" value={vsDraft?.provider || 'edge'}
                      onChange={e => setVsDraft(d => ({ ...d, provider: e.target.value }))}>
                      <option value="edge">edge-tts 在线（零显存·免费）</option>
                      <option value="local_http">本地 HTTP 服务（自建引擎）</option>
                    </select>
                  </CfgField>
                  <CfgField label="本地服务地址" hint="如 http://127.0.0.1:9880">
                    <input className="cfg-input" value={vsDraft?.url || ''}
                      onChange={e => setVsDraft(d => ({ ...d, url: e.target.value }))} />
                  </CfgField>
                  <CfgField label="服务协议" hint="决定请求路径与入参形状">
                    <select className="cfg-select" value={vsDraft?.api || 'gpt-sovits'}
                      onChange={e => setVsDraft(d => ({ ...d, api: e.target.value }))}>
                      <option value="gpt-sovits">GPT-SoVITS（POST /tts）</option>
                      <option value="openai">OpenAI 兼容（POST /v1/audio/speech）</option>
                    </select>
                  </CfgField>
                  <CfgField label="请求超时（秒）" hint="本地首条合成慢时可调到 120">
                    <input className="cfg-input" type="number" min="5" max="600"
                      value={vsDraft?.timeout ?? 60}
                      onChange={e => setVsDraft(d => ({ ...d, timeout: Number(e.target.value) }))} />
                  </CfgField>
                </div>
                <div className="cfg-tip">
                  内置 14 个 edge 音色固定走 edge-tts（不受这里切换影响），只有「来源=本地」的音色走本地服务。
                  本地音色的 voice id 由服务端决定：GPT-SoVITS 填参考音频名/角色名，OpenAI 兼容填 voice 名。
                </div>
                {probe && (
                  <div className={'vs-probe ' + (probe.ok && probe.reachable ? 'ok' : 'bad')}>
                    {probe.ok && probe.reachable
                      ? `✅ 服务可达（HTTP ${probe.status}，${probe.ms}ms）${probe.voices && probe.voices.length ? `，列出 ${probe.voices.length} 个音色` : '，未提供音色列表接口'}`
                      : `❌ 连不上 ${probe.url || ''}：${probe.error || '服务无响应'}`}
                  </div>
                )}
                {probe && probe.voices && probe.voices.length > 0 && (
                  <div className="vs-probe ok">服务音色：{probe.voices.join(' / ')}</div>
                )}
              </div>

              <div className="cfg-group" data-tab="tts">
                <div className="cfg-group-title">音色清单
                  <span className="cfg-badge">{vs.count} 个 · {vs.groups.length} 组</span>
                </div>
                <div className="vs-table">
                  {vs.groups.map(g => (
                    <div className="vs-grp" key={g.group}>
                      <div className="vs-grp-name">{g.group}</div>
                      {(g.items || []).map(it => (
                        <div className="vs-row" key={it.key}>
                          <span className="vs-label">{it.label}</span>
                          <code className="vs-voice">{it.voice}</code>
                          <span className="vs-gender">{it.gender === 'f' ? '女' : it.gender === 'm' ? '男' : '—'}</span>
                          <span className={'vs-src' + (it.provider === 'local' ? ' local' : '')}>
                            {it.provider === 'local'
                              ? (vsDraft?.provider === 'local_http' ? '本地·启用' : '本地·未启用')
                              : '在线'}
                          </span>
                          <button className="small ghost" onClick={() => previewVoice(it.voice)} title="试听">🔊</button>
                          {vs.builtin_keys.indexOf(it.key) < 0
                            ? <button className={'small ghost vs-del' + (confirmDel === it.key ? ' armed' : '')}
                                disabled={!!vsBusy}
                                onClick={() => delVsItem(it.key, it.label)}>
                                {confirmDel === it.key ? '确认删' : '删'}
                              </button>
                            : <span className="vs-del-ph" title="内置音色不可删" />}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
                <div className="vs-add">
                  <div className="vs-add-title">添加本地音色</div>
                  <div className="vs-add-row">
                    <input className="cfg-input" placeholder="分组（如 本地音色）" value={newVoice.group}
                      onChange={e => setNewVoice(n => ({ ...n, group: e.target.value }))} />
                    <input className="cfg-input" placeholder="显示名（如 林越·低沉）" value={newVoice.label}
                      onChange={e => setNewVoice(n => ({ ...n, label: e.target.value }))} />
                    <input className="cfg-input" placeholder="voice id（服务里的音色/参考音频名）" value={newVoice.voice}
                      onChange={e => setNewVoice(n => ({ ...n, voice: e.target.value }))} />
                    <select className="cfg-select" value={newVoice.gender}
                      onChange={e => setNewVoice(n => ({ ...n, gender: e.target.value }))}>
                      <option value="f">女声</option>
                      <option value="m">男声</option>
                    </select>
                    <button className="small" disabled={!!vsBusy} onClick={addVsItem}>
                      {vsBusy === 'add' ? '添加中…' : '添加'}
                    </button>
                  </div>
                  <div className="cfg-tip">新音色写进 data/voice_sources.yaml，配音页下拉立即出现；本地音色只有「音色源类型=本地 HTTP 服务」时才真正调服务。</div>
                </div>
              </div>

              <div className="cfg-group" data-tab="tts">
                <div className="cfg-group-title">本地音色库
                  <span className="cfg-badge">
                    {lib ? `${lib.stats.total} 款 · 已下载 ${lib.stats.downloaded}` : '读取中…'}
                  </span>
                </div>
                <div className="lib-bar">
                  <input className="cfg-input" placeholder="搜名称 / 编号 / 分类 / 标签"
                    value={libQ} onChange={e => setLibQ(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') loadLib(1) }} />
                  <select className="cfg-select" value={libGender}
                    onChange={e => { setLibGender(e.target.value); loadLib(1, libQ, e.target.value, libCat) }}>
                    <option value="">全部性别</option>
                    <option value="f">女声</option>
                    <option value="m">男声</option>
                  </select>
                  <select className="cfg-select" value={libCat}
                    onChange={e => { setLibCat(e.target.value); loadLib(1, libQ, libGender, e.target.value) }}>
                    <option value="">全部分类</option>
                    {(lib?.stats.categories || []).map(c => (
                      <option key={c.key} value={c.key}>{c.name}（{c.count}）</option>
                    ))}
                  </select>
                  <button className="small" disabled={libBusy === 'load'} onClick={() => loadLib(1)}>
                    {libBusy === 'load' ? '读取中…' : '搜索'}
                  </button>
                </div>
                <div className="cfg-tip">
                  1248 款真实录音参考音频（公开音色库 voice.jimu.chat），落在 backend/data/voice_library/。
                  「试听」直接播原声样本（不经过 TTS）；「加入清单」写进 voice_sources.yaml（voice 填参考音频绝对路径），
                  接上 GPT-SoVITS / CosyVoice 后即可用它做 zero-shot 配音。
                </div>
                {lib && <>
                  <div className="lib-list">
                    {lib.items.map(it => (
                      <div className="lib-row" key={it.code}>
                        <code className="lib-code">{it.code}</code>
                        <span className="lib-name" title={it.sampleText || it.name}>{it.name}</span>
                        <span className="lib-gender">{it.gender === 'f' ? '女' : it.gender === 'm' ? '男' : '—'}</span>
                        <span className="lib-cat">{it.categoryName} · {it.emotionName}</span>
                        <span className={'lib-state' + (it.downloaded ? ' ok' : '')}>
                          {it.downloaded ? `${Math.round(it.size / 1024)}K` : '未下载'}
                        </span>
                        <button className="small ghost" disabled={!it.downloaded}
                          onClick={() => { new Audio(`/api/voice-library/${it.code}/audio?ts=${Date.now()}`).play() }}>🔊</button>
                        <button className="small" disabled={!it.downloaded || !!libBusy}
                          onClick={() => addLibItem(it.code, it.name)}>
                          {libBusy === 'add:' + it.code ? '加入中…' : '加入'}
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="lib-pager">
                    <button className="small ghost" disabled={lib.page <= 1} onClick={() => loadLib(lib.page - 1)}>上一页</button>
                    <span>第 {lib.page} / {lib.pages} 页 · 共 {lib.total} 款{(libQ || libGender || libCat) ? '（已筛选）' : ''}</span>
                    <button className="small ghost" disabled={lib.page >= lib.pages} onClick={() => loadLib(lib.page + 1)}>下一页</button>
                    <button className="small" disabled={!!libBusy} onClick={addLibBatch}>
                      {libBusy === 'batch' ? '加入中…' : `批量加入本页（${lib.items.length}）`}
                    </button>
                  </div>
                </>}
                {libMsg && <div className="vs-probe ok">{libMsg}</div>}
                {!lib && <div className="cfg-note">正在读取音色库索引…</div>}
              </div>
            </>}
            {!vs && <div className="cfg-note">正在读取音色源…</div>}
          </div>

          <div className="cfg-actions">
            {tab === 'tts' ? <>
              <div className="cfg-msg">{vsMsg}</div>
              <div className="cfg-btns">
                <button className="ghost" disabled={!!vsBusy} onClick={probeVs}>
                  {vsBusy === 'probe' ? '探测中…' : '测试连接'}
                </button>
                <button disabled={!!vsBusy} onClick={saveVsSource}>
                  {vsBusy === 'save' ? '保存中…' : '保存音色源'}
                </button>
              </div>
            </> : <>
              <div className="cfg-msg">{msg}</div>
              <div className="cfg-btns">
                <button className="ghost" disabled={!!busy} onClick={restartComfy}>
                  {busy === 'comfy' ? '重启中…' : '重启 ComfyUI'}
                </button>
                <button disabled={!!busy} onClick={save}>{busy === 'save' ? '保存中…' : '保存配置'}</button>
              </div>
            </>}
          </div>
        </>}
      </div>
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
  const [cfgOpen, setCfgOpen] = useState(false)

  const reloadProjects = () => api('/projects').then(setProjects)
  useEffect(() => { reloadProjects() }, [])

  useEffect(() => {
    const es = new EventSource(`${API}/tasks/stream`)
    // SSE 断线重连（后端重启/机器休眠）后不会回放历史事件，页面会停在断线前的旧快照
    // （典型症状：任务库里已 done，任务栏还挂着 "running 100%"）。重连成功即全量拉一次。
    es.onopen = () => api('/tasks?limit=12').then(setTasks).catch(() => {})
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
  // 兜底对账：SSE 断线期间（EventSource 静默重连、后端卡死等）每 15 秒拉一次任务列表，
  // 保证任务栏状态与库内一致，不再出现"已完成的任务一直显示正在跑"。
  useEffect(() => {
    const h = setInterval(() => { api('/tasks?limit=12').then(setTasks).catch(() => {}) }, 15000)
    return () => clearInterval(h)
  }, [])
  useEffect(() => {
    const tick = () => api('/system').then(s => setVram(s.comfyui)).catch(() => {})
    tick()
    const h = setInterval(tick, 5000)
    return () => clearInterval(h)
  }, [])

  const project = projects.find(p => p.id === projectId)
  const refreshTasks = () => api('/tasks?limit=10').then(setTasks)
  // 页面加载/重开时先 REST 拉一次任务列表：SSE 只推增量事件，
  // 不回放正在跑的任务，缺这次拉取会导致重开页面任务栏一直"空闲"（#79）
  useEffect(() => { refreshTasks() }, [])
  const needProject = stage !== 'projects' && !project

  return (
    <>
      <div className="layout">
        <StageNav stage={stage} setStage={setStage} hasProject={!!project}
          openSettings={() => setCfgOpen(true)} />
        <div className="main">
          {needProject && <div className="empty-hint">
            <div className="page-title" style={{ fontSize: 17, marginBottom: 10 }}>还没有选中的项目</div>
            <div className="empty-hint-s">先在「项目」页选择已有作品，或新建一个项目再进入剧本 / 资产 / 分镜流程。</div>
            <button className="small accent" onClick={() => setStage('projects')}>← 回项目中心</button>
          </div>}
          {stage === 'projects' && <ProjectsPage projects={projects} reload={reloadProjects} selectProject={id => { setProjectId(id); setStage('script') }} />}
          {stage === 'script' && project && <ScriptPage project={project} refreshTasks={refreshTasks} setStage={setStage} setAssetsVersion={setAssetsVersion} key={project.id} />}
          {stage === 'assets' && project && <AssetsPage project={{ ...project, _assetsVersion: assetsVersion }} refreshTasks={refreshTasks} setStage={setStage} />}
          {stage === 'storyboard' && project && <StoryboardPage project={project} setStage={setStage} />}
          {stage === 'voice' && project && <ExportPage project={project} setStage={setStage} wizardStage="voice" />}
          {stage === 'export' && project && <ExportPage project={project} setStage={setStage} />}
        </div>
      </div>
      <TaskBar tasks={tasks} vram={vram} refreshTasks={refreshTasks} />
      <SettingsModal open={cfgOpen} onClose={() => setCfgOpen(false)} />
    </>
  )
}
