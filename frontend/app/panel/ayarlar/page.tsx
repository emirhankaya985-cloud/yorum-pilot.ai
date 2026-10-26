'use client';
import {PanelShell} from '@/components/PanelShell';import {useState,useEffect} from 'react';import {api} from '@/lib/api';import {Building2,ShieldAlert,Bell,Settings2,Globe2} from 'lucide-react';
export default function SettingsPage(){return <PanelShell>{(_,org)=><SettingsContent org={org}/>}</PanelShell>}
function SettingsContent({org}:{org:string}){const [locations,setLocations]=useState<{id:string;name:string;demo:boolean}[]>([]);useEffect(()=>{api<{id:string;name:string;demo:boolean}[]>(`/organizations/${org}/locations`).then(setLocations).catch(()=>{})},[org]);return <><div className="page-heading"><div><div className="eyebrow">ÇALIŞMA ALANI</div><h1>Ayarlar</h1><p>Bağlantı durumunuzu ve demo şubelerinizi görüntüleyin.</p></div></div><div className="settings-grid"><section className="panel-card settings-card"><span className="settings-icon"><Globe2 size={22}/></span><h2>Google Business Profile</h2><p>Resmî API erişimi doğrulanmadığı için bağlantı ve gerçek yorum işlemleri henüz etkin değildir.</p><span className="disabled-pill"><ShieldAlert size={15}/> API ERİŞİMİ BEKLENİYOR</span><button disabled className="btn btn-light full">Google İşletme Hesabımı Bağla (yakında)</button></section><section className="panel-card settings-card"><span className="settings-icon"><Building2 size={22}/></span><h2>İşletmeler ve şubeler</h2><p>Demo hesabınıza bağlı sentetik şubeler.</p>{locations.map(x=><div className="settings-location" key={x.id}><Building2 size={17}/><div><strong>{x.name}</strong><small>Demo şube</small></div></div>)}</section><section className="panel-card settings-card"><span className="settings-icon"><Bell size={22}/></span><h2>Bildirim kanalları</h2><p>Özel mesajla güvenli eşleştirme; Google'a otomatik cevap gönderilmez.</p><TelegramConnect org={org}/><p>ntfy hesabı bağlantısı henüz ayrı olarak yapılandırılmadı.</p></section><section className="panel-card settings-card"><span className="settings-icon"><Settings2 size={22}/></span><h2>AI modeli</h2><p>Şu anda kural tabanlı çevrimdışı yanıt motoru aktiftir. Gerçek LLM sağlayıcısı henüz bağlı değil.</p><span className="disabled-pill">OFFLINE DEMO MODE</span></section></div></>}

type TelegramStatus={bot_configured:boolean;bot_username:string;linked:boolean;mode:string;real_google_publish:boolean};
function TelegramConnect({org}:{org:string}){
  const [status,setStatus]=useState<TelegramStatus|null>(null);
  const [link,setLink]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(()=>{setLink('');setMessage('');api<TelegramStatus>(`/organizations/${org}/telegram/status`).then(setStatus).catch(()=>setMessage('Telegram durumu alınamadı.'))},[org]);
  async function execute(action:'pair'|'test'|'disconnect'){
    setBusy(true);setMessage('');
    try {
      if(action==='pair'){
        const result=await api<{deep_link:string;expires_minutes:number}>(`/organizations/${org}/telegram/pair`,{method:'POST'});
        setLink(result.deep_link);setMessage('Bağlantı 10 dakika geçerlidir. Telegram botunu aç ve Başlat düğmesine bas.');
      } else if(action==='test'){
        await api(`/organizations/${org}/telegram/test`,{method:'POST'});
        setMessage('Sentetik test bildirimi Telegram sohbetine gönderildi.');
      } else {
        await api(`/organizations/${org}/telegram/disconnect`,{method:'POST'});
        setLink('');setMessage('Telegram bağlantısı kaldırıldı.');
      }
      setStatus(await api<TelegramStatus>(`/organizations/${org}/telegram/status`));
    } catch(error){setMessage(error instanceof Error?error.message:'İşlem başarısız');}
    finally{setBusy(false);}
  }
  return <div style={{display:'grid',gap:12,marginTop:12}}>
    {!status&&<span>Bağlantı kontrol ediliyor...</span>}
    {status&&!status.bot_configured&&<span className="disabled-pill">BOTFATHER TOKEN BEKLENİYOR — Render API ortamına TELEGRAM_BOT_TOKEN ekle</span>}
    {status?.bot_configured&&<span className="disabled-pill">{status.linked?'TELEGRAM BAĞLI':'BOT HAZIR / EŞLEŞTİRME BEKLENİYOR'}</span>}
    {status?.bot_configured&&!status.linked&&<button disabled={busy} className="btn btn-light full" onClick={()=>execute('pair')}>Telegram hesabımı bağla</button>}
    {link&&<a className="btn btn-primary full" target="_blank" rel="noopener noreferrer" href={link}>Telegram botunu aç ve Başlat</a>}
    {status?.linked&&<><button disabled={busy} className="btn btn-primary full" onClick={()=>execute('test')}>Telefonuma test bildirimi gönder</button>
      <button disabled={busy} className="btn btn-light full" onClick={()=>execute('disconnect')}>Telegram bağlantısını kaldır</button></>}
    {message&&<small role="status">{message}</small>}
  </div>;
}
