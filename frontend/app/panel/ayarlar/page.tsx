'use client';
import {PanelShell} from '@/components/PanelShell';import {useState,useEffect} from 'react';import {api} from '@/lib/api';import {Building2,ShieldAlert,Bell,Settings2,Globe2} from 'lucide-react';
export default function SettingsPage(){return <PanelShell>{(_,org)=><SettingsContent org={org}/>}</PanelShell>}
function SettingsContent({org}:{org:string}){const [locations,setLocations]=useState<{id:string;name:string;demo:boolean}[]>([]);useEffect(()=>{api<{id:string;name:string;demo:boolean}[]>(`/organizations/${org}/locations`).then(setLocations).catch(()=>{})},[org]);return <><div className="page-heading"><div><div className="eyebrow">ÇALIŞMA ALANI</div><h1>Ayarlar</h1><p>Bağlantı durumunuzu ve demo şubelerinizi görüntüleyin.</p></div></div><div className="settings-grid"><section className="panel-card settings-card"><span className="settings-icon"><Globe2 size={22}/></span><h2>Google Business Profile</h2><p>Resmî API erişimi doğrulanmadığı için bağlantı ve gerçek yorum işlemleri henüz etkin değildir.</p><span className="disabled-pill"><ShieldAlert size={15}/> API ERİŞİMİ BEKLENİYOR</span><GoogleBusinessConnect org={org}/></section><section className="panel-card settings-card"><span className="settings-icon"><Building2 size={22}/></span><h2>İşletmeler ve şubeler</h2><p>Demo hesabınıza bağlı sentetik şubeler.</p>{locations.map(x=><div className="settings-location" key={x.id}><Building2 size={17}/><div><strong>{x.name}</strong><small>Demo şube</small></div></div>)}</section><section className="panel-card settings-card"><span className="settings-icon"><Bell size={22}/></span><h2>Bildirim kanalları</h2><p>Özel mesajla güvenli eşleştirme; Google'a otomatik cevap gönderilmez.</p><TelegramConnect org={org}/><p>ntfy hesabı bağlantısı henüz ayrı olarak yapılandırılmadı.</p></section><section className="panel-card settings-card"><span className="settings-icon"><Settings2 size={22}/></span><h2>AI modeli</h2><p>Şu anda kural tabanlı çevrimdışı yanıt motoru aktiftir. Gerçek LLM sağlayıcısı henüz bağlı değil.</p><span className="disabled-pill">OFFLINE DEMO MODE</span></section></div></>}

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


type GoogleState={connected:boolean;approval_gate:boolean;live_google_publish_enabled:boolean};
type GoogleAccount={name:string};
type GoogleLocation={name:string;title:string};

function GoogleBusinessConnect({org}:{org:string}){
 const [status,setStatus]=useState<GoogleState|null>(null);
 const [accounts,setAccounts]=useState<GoogleAccount[]>([]);
 const [account,setAccount]=useState('');
 const [locations,setLocations]=useState<GoogleLocation[]>([]);
 const [selected,setSelected]=useState('');
 const [activeLocation,setActiveLocation]=useState('');
 const [message,setMessage]=useState('');
 const [busy,setBusy]=useState(false);
 useEffect(()=>{setMessage('');api<GoogleState>(`/organizations/${org}/google/status`).then(setStatus).catch(()=>setMessage('Google bağlantı durumu alınamadı.'))},[org]);
 async function task(action:'start'|'accounts'|'locations'|'select'|'sync'|'disconnect'){
  setBusy(true);setMessage('');
  try{
   if(action==='start'){
     const result=await api<{authorization_url:string}>(`/organizations/${org}/google/start`,{method:'POST'});
     // OAuth URL contains only public client ID, PKCE challenge and state; never secrets.
     window.location.assign(result.authorization_url);return;
   }
   if(action==='accounts'){
     const res=await api<{accounts:GoogleAccount[]}>(`/organizations/${org}/google/accounts`);
     setAccounts(res.accounts);setMessage(`${res.accounts.length} erişilebilir Google hesabı listelendi.`);
   }
   if(action==='locations'){
     const id=account.startsWith('accounts/')?account.slice('accounts/'.length):'';
     if(!/^\d+$/.test(id))throw new Error('Önce Google hesabını seç.');
     const res=await api<{locations:GoogleLocation[]}>(`/organizations/${org}/google/accounts/${id}/locations`);
     setLocations(res.locations);setSelected('');setMessage(`${res.locations.length} şube listelendi.`);
   }
   if(action==='select'){
     const result=await api<{location_id:string;real_google_location:boolean}>(`/organizations/${org}/google/select-location`,
       {method:'POST',body:JSON.stringify({account_name:account,location_name:selected})});
     setActiveLocation(result.location_id);setMessage('Şube doğrulandı ve seçildi. Gerçek yorumlar henüz aktarılmadı.');
   }
   if(action==='sync'){
     const result=await api<{read:number;drafts_created_or_refreshed:number;google_replies_published:number}>(`/organizations/${org}/google/sync/${activeLocation}`,
       {method:'POST'});
     setMessage(`${result.read} yorum okundu, ${result.drafts_created_or_refreshed} taslak güncellendi. Google yanıtı: 0.`);
   }
   if(action==='disconnect'){
     await api(`/organizations/${org}/google/disconnect`,{method:'POST'});
     setStatus({connected:false,approval_gate:status?.approval_gate??false,live_google_publish_enabled:false});
     setAccounts([]);setLocations([]);setSelected('');setActiveLocation('');
     setMessage('Yerel bağlantı iptal edildi. Google hesabından uygulama yetkisini de kaldırabilirsiniz.');
   }
  }catch(err){setMessage(err instanceof Error?err.message:'Google işlemi başarısız');}
  finally{setBusy(false);}
 }
 return <div style={{display:'grid',gap:12,marginTop:12}}>
  {!status&&<span>OAuth durumu kontrol ediliyor...</span>}
  {status&&!status.approval_gate&&<span className="disabled-pill">GOOGLE BUSINESS PROFILE API ONAYI BEKLENİYOR</span>}
  {status?.approval_gate&&!status.connected&&<button disabled={busy} className="btn btn-primary full" onClick={()=>task('start')}>Google işletme sahibini yetkilendir</button>}
  {status?.connected&&<><span>Google erişimi bağlı — otomatik yanıt kapalı</span>
   <button disabled={busy} className="btn btn-light full" onClick={()=>task('accounts')}>Yetkili hesapları listele</button>
   {!!accounts.length&&<select aria-label="Google hesabı" value={account} onChange={e=>setAccount(e.target.value)}><option value="">Google hesabı seç</option>{accounts.map(a=><option key={a.name} value={a.name}>{a.name}</option>)}</select>}
   {!!account&&<button disabled={busy} className="btn btn-light full" onClick={()=>task('locations')}>Şubeleri listele</button>}
   {!!locations.length&&<select aria-label="Google şubesi" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Şube seç</option>{locations.map(l=><option key={l.name} value={l.name}>{l.title}</option>)}</select>}
   {!!selected&&<button disabled={busy} className="btn btn-light full" onClick={()=>task('select')}>Bu şubeyi bağla</button>}
   {!!activeLocation&&<button disabled={busy} className="btn btn-primary full" onClick={()=>task('sync')}>Yorumları oku ve taslak hazırla</button>}
   <button disabled={busy} className="btn btn-light full" onClick={()=>task('disconnect')}>Google bağlantısını kes</button>
  </>}
  {message&&<small role="status">{message}</small>}
  <small>Yalnızca sahip izinli gerçek şubeler; demo kayıtları ayrı kalır. Google'a yanıt gönderilmez.</small>
 </div>;
}
