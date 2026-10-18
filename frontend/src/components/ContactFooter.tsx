import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BrandMark, Icon } from './Icon'
const email='1826244602@qq.com'
const groups=[
 {title:'识别服务',links:[['/detect','图片识别'],['/video','视频识别'],['/history','历史记录']]},
 {title:'使用与了解',links:[['/features','核心能力'],['/about','技术介绍'],['/statistics','数据统计']]},
 {title:'项目支持',links:[['/deployment','源码与部署'],['mailto:'+email,'项目交流']]},
]
export function ContactFooter(){
 const [message,setMessage]=useState('')
 async function copy(){try{await navigator.clipboard.writeText(email);setMessage('邮箱已复制')}catch{setMessage('复制失败，请手动复制上方邮箱')}}
 return <footer id="contact" className="contact-footer" aria-labelledby="contact-title"><div className="footer-services">{[['图片识别',1],['视频分析',2],['记录追溯',3],['植保建议',5]].map(([label,index])=><div key={String(label)}><Icon index={Number(index)}/><span>{label}</span></div>)}</div><div className="footer-main"><div className="footer-link-groups">{groups.map(group=><nav key={group.title} aria-label={group.title}><h3>{group.title}</h3>{group.links.map(([to,label])=>to.startsWith('mailto:')?<a key={to} href={to}>{label}</a>:<Link key={to} to={to}>{label}</Link>)}</nav>)}</div><section className="footer-contact"><p className="footer-contact-kicker">LET’S CONNECT</p><h2 id="contact-title">联系我们</h2><p>项目交流、数据合作与部署咨询</p><a className="contact-email" href={'mailto:'+email}>{email}</a><div className="contact-actions"><a className="contact-mail" href={'mailto:'+email}><Icon index={8}/>邮件联系</a><button type="button" onClick={()=>void copy()}>复制邮箱</button></div><p className="contact-feedback" role="status">{message}</p></section></div><div className="footer-bottom"><Link className="footer-brand" to="/" aria-label="禾察首页"><BrandMark/><strong>禾察</strong><span>HECHA</span></Link><p>农作物害虫智能识别与植保决策平台</p><span>2026 华北五省大学生计算机应用大赛参赛作品</span></div></footer>
}
