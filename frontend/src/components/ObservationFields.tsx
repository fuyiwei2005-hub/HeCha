import { Observation } from '../api'
export function ObservationFields({value,onChange,disabled=false}:{value:Observation;onChange:(v:Observation)=>void;disabled?:boolean}) {
  const set=(key:keyof Observation,text:string)=>onChange({...value,[key]:text})
  return <fieldset className="field-context" disabled={disabled}><legend>田间信息 <small>选填，帮助连续观察与分析</small></legend>
    <div className="field-inputs"><label>地块名称<input aria-label="地块名称" className="input" value={value.field_name} maxLength={80} placeholder="如：东侧一号田" onChange={e=>set('field_name',e.target.value)}/></label>
    <label>生长阶段<select aria-label="生长阶段" className="select" value={value.growth_stage} onChange={e=>set('growth_stage',e.target.value)}>{['','苗期','营养生长期','开花期','结果期','成熟期'].map(v=><option key={v} value={v}>{v||'暂不确定'}</option>)}</select></label>
    <label>观察到的程度<select aria-label="观察到的程度" className="select" value={value.severity} onChange={e=>set('severity',e.target.value)}>{['','少量','局部明显','大面积'].map(v=><option key={v} value={v}>{v||'暂不确定'}</option>)}</select></label></div>
    <label>观察笔记<textarea aria-label="观察笔记" className="input" rows={2} value={value.notes} maxLength={1000} placeholder="发生部位、近期变化或已采取的措施" onChange={e=>set('notes',e.target.value)}/></label>
  </fieldset>
}
