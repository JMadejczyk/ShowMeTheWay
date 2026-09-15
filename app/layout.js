import './globals.css';
import '@xyflow/react/dist/style.css';
export const metadata = { title: 'ShowMeTheWay', description: 'AI roadmaps for any field' };
export default function RootLayout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}
