import SynapseApp from "@/components/synapse-app";
export default async function EvidencePage({ params }: { params: Promise<{ id: string }> }) { return <SynapseApp view="evidence" applicationId={(await params).id} />; }
