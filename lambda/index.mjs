export const handler = async (event) => {
  const payload = JSON.parse(event.body);
  const repo = payload.repository?.full_name;

  const ALLOWED_REPO = "abhinavkumar17/arch-drift-detection";

  if (repo !== ALLOWED_REPO) {
    console.log("Discarding event from unexpected repo:", repo);
    return { statusCode: 200, body: "Ignored" };
  }

  const packet = {
    repo: repo,
    prNumber: payload.pull_request?.number,
    githubToken: process.env.GITHUB_TOKEN,
    modelApiKeys: {
      openrouter: "DUMMY_KEY_FOR_NOW"
    }
  };

  console.log("Packet ready:", JSON.stringify(packet, null, 2));

  return { statusCode: 200, body: "OK" };
};
