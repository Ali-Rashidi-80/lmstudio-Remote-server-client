export default function Loading() {
  return (
    <main className="auth-wrap">
      <div className="card-form" style={{ gap: "0.75rem" }}>
        <div className="skeleton" style={{ width: "55%", height: 22 }} />
        <div className="skeleton" style={{ width: "100%", height: 14 }} />
        <div className="skeleton" style={{ width: "80%", height: 14 }} />
      </div>
    </main>
  );
}
