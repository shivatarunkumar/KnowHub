/**
 * The four diagrams on the About page. They describe what the code does today, not the
 * end-state design — anything not built yet is drawn dashed and labelled "planned".
 */

import { Arrow, Box, Figure, Lane, Step } from "./parts";

export function SystemDiagram() {
  return (
    <Figure
      title="High level: what talks to what"
      caption="Video bytes go straight from the browser to Cloud Storage; everything else goes through the API. Each external service sits behind an adapter, so the local and GCP setups run the same code."
      viewBox="0 0 900 400"
    >
      <Box x={20} y={150} w={150} h={76} title="Browser" lines={["watch, upload,", "comment"]} tone="brand" />
      <Box x={240} y={150} w={150} h={76} title="web" lines={["Next.js 16", "server-rendered"]} />
      <Box x={460} y={150} w={150} h={76} title="api" lines={["FastAPI", "/api/v1/*"]} />

      <Box x={700} y={30} w={170} h={70} title="PostgreSQL 17" lines={["users, videos,", "comments, audit"]} tone="store" />
      <Box x={700} y={130} w={170} h={70} title="Cloud Storage" lines={["knowhub-data", "raw/ + media/"]} tone="store" />
      <Box x={700} y={230} w={170} h={62} title="Ollama" lines={["writing assist"]} tone="store" />
      <Box x={700} y={320} w={170} h={62} title="Pub/Sub" lines={["topics ready, no", "consumers yet"]} tone="ghost" />

      <Arrow from={[170, 188]} to={[240, 188]} label="HTTP" />
      <Arrow from={[390, 178]} to={[460, 178]} label="server render" />
      <Arrow from={[460, 200]} to={[390, 200]} label="/api proxy" dashed labelAbove={false} />
      <Arrow from={[610, 170]} to={[700, 90]} label="SQL" />
      <Arrow from={[610, 188]} to={[700, 165]} label="files" />
      <Arrow from={[610, 205]} to={[700, 258]} label="prompts" />
      <Arrow from={[610, 220]} to={[700, 345]} dashed />

      {/* the one path that bypasses the API */}
      <path
        d="M95 150 C 95 40, 400 20, 700 150"
        fill="none"
        stroke="var(--brand)"
        strokeWidth={1.8}
        markerEnd="url(#arrow-accent)"
      />
      <text x={400} y={35} textAnchor="middle" fontSize={11.5} fontWeight={600} fill="var(--brand)">
        video file — 8 MB resumable chunks, direct to Cloud Storage
      </text>
    </Figure>
  );
}

export function UploadFlow() {
  const browser = 130;
  const api = 450;
  const store = 780;
  return (
    <Figure
      title="How a video gets saved in Cloud Storage"
      caption="The API never touches the file itself — it only hands out an upload session and, at the end, checks the object really arrived. That is what makes multi-GB uploads possible and resumable."
      viewBox="0 0 900 470"
    >
      <Lane x={browser} label="Browser" sub="upload form" top={10} bottom={440} />
      <Lane x={api} label="api (FastAPI)" sub="+ PostgreSQL" top={10} bottom={440} />
      <Lane x={store} label="Cloud Storage" sub="knowhub-data" top={10} bottom={440} />

      <Step n={1} fromX={browser} toX={api} y={90} label="POST /videos/uploads/start" note="name, size, type, title, topic" />
      <Step n={2} fromX={api} toX={store} y={140} label="open a resumable session" note="also INSERT videos (UPLOADING) + upload_events" />
      <Step n={3} fromX={api} toX={browser} y={190} label="video_id + upload_url + chunk_size" />
      <Step n={4} fromX={browser} toX={store} y={245} label="PUT 8 MB chunk → 308 Resume Incomplete" note="repeats to the end; retries with backoff" accent />
      <Step n={5} fromX={browser} toX={api} y={305} label="POST /videos/{id}/complete" />
      <Step n={6} fromX={api} toX={store} y={350} label="stat the object: is it really there?" note="size recorded; missing ⇒ status FAILED" />
      <Step n={7} fromX={browser} toX={api} y={405} label="POST /videos/{id}/thumbnail" note="frame captured from the file in a canvas" />

    </Figure>
  );
}

export function StorageLayout() {
  return (
    <Figure
      title="Where the bytes land"
      caption="One bucket, two prefixes. Each user's originals sit under their own folder, which is what the per-user isolation check on the API relies on."
      viewBox="0 0 900 250"
    >
      <Box x={40} y={30} w={820} h={40} title="gs://knowhub-data" tone="brand" />

      <Box x={40} y={110} w={390} h={100} title="raw/  — the original file" lines={["users/{user_id}/videos/{video_id}/source.mp4", "written once, by the browser", "private: never served directly"]} tone="store" />
      <Box x={470} y={110} w={390} h={100} title="media/  — everything derived" lines={["videos/{video_id}/thumbs/default.jpg", "videos/{video_id}/hls/…  (planned)", "served through the API today"]} tone="store" />

      <Arrow from={[235, 70]} to={[235, 110]} />
      <Arrow from={[665, 70]} to={[665, 110]} />
    </Figure>
  );
}

export function AuthFlow() {
  const browser = 130;
  const api = 450;
  const db = 780;
  return (
    <Figure
      title="How signing in works"
      caption="The password is checked once; after that every request carries a short-lived signed token. The long-lived half lives only in the database as a hash, so a database leak cannot be replayed as a login."
      viewBox="0 0 900 430"
    >
      <Lane x={browser} label="Browser" sub="httpOnly cookies" top={10} bottom={400} />
      <Lane x={api} label="api" sub="argon2id + PyJWT" top={10} bottom={400} />
      <Lane x={db} label="PostgreSQL" sub="users, refresh_tokens" top={10} bottom={400} />

      <Step n={1} fromX={browser} toX={api} y={90} label="POST /auth/register or /auth/login" note="email + password" />
      <Step n={2} fromX={api} toX={db} y={140} label="look up the user, verify the argon2id hash" note="5 failures ⇒ locked for 15 minutes" />
      <Step n={3} fromX={api} toX={db} y={195} label="store SHA-256(refresh token)" note="the token itself is never saved" />
      <Step n={4} fromX={api} toX={browser} y={245} label="Set-Cookie: access (15 min) + refresh (14 days)" accent />
      <Step n={5} fromX={browser} toX={api} y={300} label="every later request sends the access cookie" note="decoded and verified with JWT_SECRET" />
      <Step n={6} fromX={browser} toX={api} y={360} label="POST /auth/refresh when it expires" note="old token revoked, new pair issued — reuse revokes the family" />
    </Figure>
  );
}

export function EngagementDiagram() {
  return (
    <Figure
      title="How likes, comments and shares are stored"
      caption="Reactions are one row per person per video, so a second click just updates or deletes that row. The counters on videos are copies kept in step by the API, so a feed of 24 cards stays one query."
      viewBox="0 0 900 430"
    >
      <Box
        x={340}
        y={30}
        w={220}
        h={118}
        title="videos"
        lines={["id, owner_id, title", "visibility, comments_enabled", "view_count · like_count", "comment_count  ← copies"]}
        tone="brand"
      />

      <Box x={30} y={210} w={210} h={92} title="video_reactions" lines={["PK (user_id, video_id)", "value: +1 like / −1 dislike", "clearing deletes the row"]} tone="store" />
      <Box x={280} y={210} w={230} h={110} title="comments" lines={["video_id, user_id, body", "parent_id → comments.id", "one level: a reply to a reply", "joins the same thread"]} tone="store" />
      <Box x={550} y={210} w={150} h={92} title="comment_reactions" lines={["PK (user_id,", "comment_id)"]} tone="store" />
      <Box x={730} y={210} w={140} h={92} title="video_shares" lines={["to_user_id,", "message, at_seconds"]} tone="store" />

      <Box x={280} y={350} w={230} h={60} title="notifications" lines={["reply · @mention · share"]} tone="store" />
      <Box x={30} y={350} w={210} h={60} title="watch_history" lines={["planned"]} tone="ghost" />

      <Arrow from={[400, 148]} to={[180, 210]} />
      <Arrow from={[430, 148]} to={[400, 210]} />
      <Arrow from={[490, 148]} to={[620, 210]} dashed />
      <Arrow from={[530, 148]} to={[790, 210]} />
      <Arrow from={[395, 320]} to={[395, 350]} label="" />
      <Arrow from={[510, 265]} to={[550, 258]} />
    </Figure>
  );
}
