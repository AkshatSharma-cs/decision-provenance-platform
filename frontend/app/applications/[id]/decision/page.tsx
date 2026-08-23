import SynapseApp from "@/components/synapse-app";
export default async function DecisionPage({ params }: { params: Promise<{ id: string }> }) { return <SynapseApp view="decision" applicationId={(await params).id} />; }
