export type Organization = {id:string; name:string; role:string};
export type CurrentUser = {email:string;organizations:Organization[]};
export type Dashboard = {source:string;location_count:number;review_count:number;pending_count:number;negative_count:number;draft_count:number;simulated_published_count:number;google_connected:boolean;average_stars:number|null};
export type Review = {id:string; location_id:string;location:string;stars:number;content:string;sentiment:string;priority:string;category:string;status:string;created_at:string;draft:string|null;approved:boolean;source:string};

function csrfCookie():string {
  if(typeof document === 'undefined') return '';
  return decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('yp_csrf='))?.split('=')[1] ?? '');
}

export async function api<T>(path:string, init:RequestInit={}):Promise<T> {
  const method=(init.method??'GET').toUpperCase();
  const headers=new Headers(init.headers);
  if(init.body) headers.set('Content-Type','application/json');
  if(!['GET','HEAD','OPTIONS'].includes(method)) headers.set('X-CSRF-Token',csrfCookie());
  const response=await fetch(`/api${path}`,{...init,headers,credentials:'include',cache:'no-store'});
  if(!response.ok){
    let msg=`İstek başarısız (HTTP ${response.status})`;
    try{const b=await response.json();if(typeof b.detail==='string')msg=b.detail;}catch{}
    throw new Error(msg);
  }
  return response.json() as Promise<T>;
}
