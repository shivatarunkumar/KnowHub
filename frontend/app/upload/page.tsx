import { redirect } from "next/navigation";
import { UploadForm } from "@/components/UploadForm";
import { getTopics } from "@/lib/api";
import { getCurrentUser } from "@/lib/session";

export const metadata = { title: "Upload · KnowHub" };

export default async function UploadPage() {
  const [user, topics] = await Promise.all([getCurrentUser(), getTopics()]);
  if (!user) redirect("/login?next=/upload"); // uploading needs an account
  return <UploadForm topics={topics} />;
}
