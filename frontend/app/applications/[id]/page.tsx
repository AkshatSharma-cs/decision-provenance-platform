import SynapseApp from "@/components/synapse-app";
export default async function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  return <SynapseApp view="dashboard" applicationId={(await params).id} />;
}
