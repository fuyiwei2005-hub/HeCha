const paths = [
'M3 11 12 3l9 8M5 10v10h14V10M9 20v-6h6v6',
'M4 7h4l2-3h4l2 3h4v13H4ZM8 13a4 4 0 1 0 8 0 4 4 0 0 0-8 0',
'M3 5h13v14H3ZM16 10l5-3v10l-5-3',
'M4 5h16v16H4ZM8 3v4M16 3v4M8 11h8M8 15h5',
'M5 20V10M12 20V4M19 20v-7',
'M12 3v18M3 12h18M6 6l12 12M18 6 6 18',
'M5 20V4h14v16ZM9 8h6M9 12h6M9 16h3',
'M12 3 3 8l9 5 9-5-9-5ZM3 12l9 5 9-5M3 16l9 5 9-5',
'M3 6h18v14H3ZM3 6l9 7 9-7',
'M8 7 3 12l5 5M16 7l5 5-5 5M14 4l-4 16'
]
export function Icon({index=0,className=''}:{index?:number;className?:string}) {return <svg className={'ui-icon '+className} width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[index%paths.length]}/></svg>}
export function BrandMark(){return <svg width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M16 27V13M16 21C6 22 4 14 5 8c8 0 12 4 11 13ZM16 16C15 8 21 4 28 4c0 8-4 12-12 12Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>}
