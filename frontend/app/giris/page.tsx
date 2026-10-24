'use client';
import {useState} from 'react';
import {useRouter} from 'next/navigation';
import Link from 'next/link';
import {Brand} from '@/components/Brand';
import {api} from '@/lib/api';
export default function Login(){
 const router=useRouter(); const [email,setEmail]=useState('');const [password,setPassword]=useState('');const [error,setError]=useState('');const [loading,setLoading]=useState(false);
 async function submit(e:React.FormEvent){e.preventDefault();setError('');setLoading(true);try{await api('/auth/login',{method:'POST',body:JSON.stringify({email,password})});router.push('/panel')}catch(err){setError((err as Error).message)}finally{setLoading(false)}}
 return <main className="auth-bg"><div className="auth-panel"><Brand/><div className="auth-box"><div className="eyebrow">TEKRAR HOŞ GELDİNİZ</div><h1>Hesabınıza giriş yapın.</h1><p>Yorumları yönetmeye kaldığınız yerden devam edin.</p><form onSubmit={submit} className="auth-form"><label>E-posta adresi<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="ornek@isletme.com" required/></label><label>Şifre<input type="password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{error&&<div className="alert-error">{error}</div>}<button disabled={loading} className="btn btn-primary btn-lg full">{loading?'Giriş yapılıyor...':'Giriş yap'}</button></form><p className="auth-bottom">Henüz hesabınız yok mu? <Link href="/kayit">Demo hesabı oluşturun</Link></p></div><span className="auth-foot">© 2026 YorumPilot AI</span></div><div className="auth-art"><div className="auth-art-inner"><span>◈ YORUMPILOT AI</span><h2>Her yorumu anlamlı bir bağlantıya dönüştürün.</h2><p>İşletmenizin dijital itibarını tek noktadan yönetin.</p><div className="art-testimonial">✨ Akıllı, güvenli ve işletmenizin kontrolünde.</div></div></div></main>
}
