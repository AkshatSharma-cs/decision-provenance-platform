import SynapseApp from "@/components/synapse-app";

export default async function ApplicationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SynapseApp view="overview" applicationId={id} />;
}
