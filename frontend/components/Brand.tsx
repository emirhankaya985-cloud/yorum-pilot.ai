import Link from 'next/link';
import {MessageSquareText} from 'lucide-react';
export function Brand({dark=false}:{dark?:boolean}){
  return <Link href="/" className={`brand ${dark?'brand-light':''}`}><span className="brand-mark"><MessageSquareText size={20} strokeWidth={2.5}/></span><span>YorumPilot<span className="brand-ai">AI</span></span></Link>;
}
