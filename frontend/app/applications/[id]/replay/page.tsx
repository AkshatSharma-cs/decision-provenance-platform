import SynapseApp from "@/components/synapse-app";
export default async function ReplayPage({ params }: { params: Promise<{ id: string }> }) { return <SynapseApp view="replay" applicationId={(await params).id} />; }
