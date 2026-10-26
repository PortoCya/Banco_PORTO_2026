export default function Carregando() {
  return (
    <div className="carregando" role="status" aria-live="polite">
      <span className="carregando-spinner" aria-hidden />
      <p>Carregando...</p>
    </div>
  );
}
