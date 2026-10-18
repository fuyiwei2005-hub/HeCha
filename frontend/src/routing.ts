export const modules = [
  ['/', '首页', '选择识别或查看记录'], ['/detect', '图片识别', '上传照片或拍照识别'],
  ['/video', '视频识别', '查看虫情时间线和视频结果'], ['/history', '历史记录', '查看结果、追问和反馈'],
  ['/statistics', '数据统计', '查看个人识别数据'], ['/features', '核心能力', '了解平台功能'],
  ['/about', '技术介绍', '了解识别与分析流程'],
  ['/deployment', '源码与部署', '了解运行方式'],
] as const
export function safeReturnPath(value: string | null): string {
  if (value === '/contact' || value === '/#contact') return '/#contact'
  return modules.some(([path]) => path === value) ? value! : '/'
}
