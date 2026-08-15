export const metadata = { title: "Architecture Q&A Agent" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#0b0f17", color: "#e6e9ef" }}>
        {children}
      </body>
    </html>
  );
}
