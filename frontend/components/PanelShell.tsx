'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';import {usePathname,useRouter} from 'next/navigation';
import {LayoutDashboard, MessageSquareText, Settings2, LogOut, Sparkles, Building2, ChevronDown, ShieldCheck} from 'lucide-react';
import {api,CurrentUser} from '@/lib/api';import {Brand} from '@/components/Brand';
export function PanelShell({children,onReady}:{children:(u:CurrentUser,orgId:string)=>React.ReactNode,onReady?:()=>void}){
 const router=useRouter(),pathname=usePathname();const [user,setUser]=useState<CurrentUser|null>(null);const [error,setError]=useState('');
 useEffect(()=>{api<CurrentUser>('/me').then(u=>{setUser(u);onReady?.()}).catch(e=>{setError(e.message);router.replace('/giris')})},[router]);
 async function logout(){try{await api('/auth/logout',{method:'POST'})}finally{router.replace('/giris')}}
 if(!user||!user.organizations.length)return <div className="page-loading">{error||'Panel yükleniyor...'}</div>;
 const orgId=user.organizations[0].id;
 const nav=[{url:'/panel',name:'Genel bakış',Icon:LayoutDashboard},{url:'/panel/yorumlar',name:'Yorumlar',Icon:MessageSquareText},{url:'/panel/ayarlar',name:'Ayarlar',Icon:Settings2}];
 return <div className="dashboard-shell"><aside className="sidebar"><div className="sidebar-brand"><Brand/></div><div className="sidebar-company"><span className="company-icon"><Building2 size={19}/></span><div><strong>{user.organizations[0].name}</strong><small>Demo çalışma alanı</small></div><ChevronDown size={14}/></div><div className="sidebar-label">ÇALIŞMA ALANI</div><nav className="sidebar-nav">{nav.map(({url,name,Icon})=><Link key={url} href={url} className={`sidebar-link ${pathname===url?'selected':''}`}><Icon size={19}/>{name}</Link>)}</nav><div className="sidebar-bottom"><div className="sidebar-promo"><div className="sidebar-promo-icon"><Sparkles size={18}/></div><strong>YorumPilot AI</strong><p>Demo modunda çalışıyor. Gerçek Google'a yanıt gönderilmez.</p></div><div className="sidebar-account"><span className="account-avatar">{user.email.charAt(0).toUpperCase()}</span><div><b>{user.email.split('@')[0]}</b><small>Hesap sahibi</small></div><button onClick={logout} aria-label="Çıkış yap" title="Çıkış yap"><LogOut size={18}/></button></div></div></aside><div className="panel-main"><div className="panel-nav"><div className="breadcrumb"><span>Çalışma alanı</span><span>/</span><strong>{pathname==='/panel'?'Genel bakış':pathname.includes('yorumlar')?'Yorumlar':'Ayarlar'}</strong></div><span className="panel-demo-badge"><ShieldCheck size={14}/> Güvenli demo</span></div><div className="panel-inner">{children(user,orgId)}</div></div></div>;
}
