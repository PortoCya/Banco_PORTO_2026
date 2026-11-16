import FormResposta from "@/components/FormResposta";

/**
 * Página pública do respondente (sem login): /pesquisa/{token}
 *
 * A pesquisa é carregada no navegador, não no servidor do Next: assim o rate
 * limit por IP da API vale para cada respondente (e não para o IP do servidor)
 * e o cookie que barra a segunda resposta no link ABERTO chega à API.
 */
export default function PaginaPesquisa({ params }: { params: { token: string } }) {
  return (
    <section className="resposta-wrap">
      <FormResposta token={params.token} />
    </section>
  );
}
