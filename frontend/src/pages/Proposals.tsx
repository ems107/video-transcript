import { Link, useSearchParams } from 'react-router-dom'
import { ProposalList } from '../knowledge'

export default function Proposals() {
  const [params] = useSearchParams()
  const video = params.get('video')
  return (
    <>
      <h1>Propuestas</h1>
      <p className="muted small" style={{ maxWidth: 820 }}>
        Lo que la IA ha aprendido de los vídeos sobre los perfiles y las personas. Nada se usa hasta que lo aceptas;
        lo rechazado no se vuelve a proponer. Puedes editar una propuesta antes de aceptarla y, si te equivocas,
        retirarla o volver a una versión anterior desde el perfil o la persona.
        {video && <> Mostrando solo un vídeo · <Link to="/propuestas">ver todas</Link></>}
      </p>
      <ProposalList query={video ? `video_id=${video}` : ''} empty="No hay propuestas pendientes." />
    </>
  )
}
