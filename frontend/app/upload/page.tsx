import { redirect } from "next/navigation";
import { UploadForm } from "@/components/UploadForm";
import { getTeams, getTopics } from "@/lib/api";
import { getCurrentUser } from "@/lib/session";

export const metadata = { title: "Upload · KnowHub" };

export default async function UploadPage() {
  const [user, topics, teams] = await Promise.all([getCurrentUser(), getTopics(), getTeams()]);
  if (!user) redirect("/login?next=/upload"); // uploading needs an account
  // the team this person uploaded under last time, so they rarely have to pick
  const defaultTeamSlug = teams.find((team) => team.id === user.team_id)?.slug ?? "";
  return <UploadForm topics={topics} teams={teams} defaultTeamSlug={defaultTeamSlug} />;
}
