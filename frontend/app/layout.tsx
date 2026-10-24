import type {Metadata} from 'next';
import './globals.css';
export const metadata: Metadata={title:'YorumPilot AI | İşletme Yorumlarını Akıllıca Yönetin', description:'Google işletme yorumları için yapay zekâ destekli, onay kontrollü profesyonel yönetim paneli.'};
export default function RootLayout({children}:{children:React.ReactNode}){
  return <html lang="tr"><body>{children}</body></html>;
}
