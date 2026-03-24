import subprocess
import json

# ══════════════════════════════════════════════════════════════════════════════
# SPECIALIST AGENTS
# Each agent does one job and returns a plain string result.
# ══════════════════════════════════════════════════════════════════════════════

def ec2_agent(instance_name: str, region: str = "us-east-1") -> str:
    """Specialist: checks EC2 instance state."""
    import tempfile, os

    cred_file = f"{os.environ.get('USERPROFILE', '')}\\Downloads\\credentials-GCCS"

    ps_content = f"""
$CredFile = "{cred_file}"
if ($CredFile -and (Test-Path $CredFile)) {{
    $creds = Get-Content $CredFile
    $Env:AWS_ACCESS_KEY_ID     = ($creds | Where-Object {{ $_ -match "^aws_access_key_id" }})     -split " = " | Select-Object -Last 1 | ForEach-Object {{ $_.Trim() }}
    $Env:AWS_SECRET_ACCESS_KEY = ($creds | Where-Object {{ $_ -match "^aws_secret_access_key" }}) -split " = " | Select-Object -Last 1 | ForEach-Object {{ $_.Trim() }}
    $Env:AWS_SESSION_TOKEN     = ($creds | Where-Object {{ $_ -match "^aws_session_token" }})     -split " = " | Select-Object -Last 1 | ForEach-Object {{ $_.Trim() }}
}}
try {{ Import-Module AWS.Tools.EC2 -ErrorAction Stop }} catch {{ Write-Output "MODULE_ERROR: AWS.Tools.EC2 not found"; exit 1 }}
try {{
    $instances = Get-EC2Instance -Region "{region}" | Select-Object -ExpandProperty Instances
    $pattern = "{instance_name}".ToLower()
    $found = @()
    foreach ($i in $instances) {{
        $name = ($i.Tags | Where-Object {{ $_.Key -eq 'Name' }}).Value
        if ($name -and $name.ToLower() -like "*$($pattern.Replace('*',''))*") {{
            $found += "$name | $($i.State.Name) | $($i.InstanceType) | $($i.PrivateIpAddress)"
        }}
    }}
    if ($found.Count -eq 0) {{ Write-Output "NO_MATCHES" }} else {{ $found | ForEach-Object {{ Write-Output $_ }} }}
}} catch {{ Write-Output "AWS_ERROR: $_" }}
"""
    tmp = tempfile.NamedTemporaryFile(suffix=".ps1", delete=False, mode="w", encoding="utf-8")
    tmp.write(ps_content)
    tmp.close()
    try:
        result = subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", tmp.name],
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout.strip()
        if output == "NO_MATCHES":
            return f"No instances found matching '{instance_name}'"
        return output if output else result.stderr.strip()
    except Exception as e:
        return f"Error: {e}"
    finally:
        os.unlink(tmp.name)


def mr_prep_agent(servers_input: str) -> str:
    """Specialist: generates MR deployment prep output."""
    servers = [s.strip() for s in servers_input.replace(",", "\n").splitlines() if s.strip()]
    pairs = []
    for s in servers:
        upper = s.upper()
        if "WADM" in upper:
            web = upper.replace("WADM", "WEB")
        elif "APP" in upper:
            web = upper.replace("APP", "WEB")
        else:
            web = upper
        pairs.append((upper, web))

    cb_srvrlst = ",".join(f"{s},{w}" for s, w in pairs)
    report_servers = "\n".join(s for s, _ in pairs)

    return (
        "#### 30mins before ####\n"
        "Run winrmfix\n"
        "Run web monitor\n"
        "Smoketest\n"
        "Run End\n\n\n"
        f"CB Srvrlst\t:\n{cb_srvrlst}\n\n\n"
        "REPORT\n"
        "Successfully applied to below assigned servers.\n"
        f"\n{report_servers}\n\n\n"
        "Enable Login:\n\nTools Used:\n\nErrors/Issues encountered:"
    )


def general_agent(question: str, history: list) -> str:
    """Specialist: answers general questions using Claude."""
    history_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in history[-6:]
    )
    prompt = f"Conversation so far:\n{history_text}\n\nUser: {question}\n\nAnswer helpfully and concisely."
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout).get("result", "")


# ══════════════════════════════════════════════════════════════════════════════
# MANAGER AGENT
# Decomposes the user's request into tasks and delegates to specialists.
# ══════════════════════════════════════════════════════════════════════════════

def manager_agent(user_input: str, history: list) -> str:
    """Manager: decides which agents to call and in what order."""

    history_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in history[-4:]
    )

    plan_prompt = f"""You are a release engineering orchestrator. Break the user's request into tasks.

Available agents:
- ec2_agent: checks EC2 state. Needs: instance_name, region (default us-east-1)
- mr_prep_agent: generates MR prep output. Needs: servers (comma-separated list)
- general_agent: answers any other question

Conversation history:
{history_text}

User request: "{user_input}"

Return a JSON array of tasks to execute IN ORDER. Each task:
{{"agent": "agent_name", "params": {{"param": "value"}}}}

Return ONLY the JSON array, no explanation. Example:
[
  {{"agent": "ec2_agent", "params": {{"instance_name": "USEADVRV1WADM26", "region": "us-east-1"}}}},
  {{"agent": "mr_prep_agent", "params": {{"servers": "USEADVRV1WADM26,USEADVRV1WADM27"}}}}
]"""

    result = subprocess.run(
        ["claude", "-p", plan_prompt, "--output-format", "json"],
        capture_output=True, text=True
    )
    raw = json.loads(result.stdout).get("result", "[]")

    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.splitlines()[:-1])

    try:
        tasks = json.loads(raw)
    except json.JSONDecodeError:
        return general_agent(user_input, history)

    # Execute each task
    results = []
    for task in tasks:
        agent = task.get("agent")
        params = task.get("params", {})

        print(f"\n[Manager] Delegating to: {agent} {params}")

        if agent == "ec2_agent":
            output = ec2_agent(params.get("instance_name", ""), params.get("region", "us-east-1"))
            results.append(f"EC2 check ({params.get('instance_name')}):\n{output}")

        elif agent == "mr_prep_agent":
            output = mr_prep_agent(params.get("servers", ""))
            results.append(f"MR Prep:\n{output}")

        elif agent == "general_agent":
            output = general_agent(params.get("question", user_input), history)
            results.append(output)

    if not results:
        return general_agent(user_input, history)

    # If only one result, return it directly
    if len(results) == 1:
        return results[0]

    # Multiple results — ask Claude to combine them into a clean summary
    combine_prompt = f"""The user asked: "{user_input}"

Multiple agents returned results:

{chr(10).join(f'--- Result {i+1} ---{chr(10)}{r}' for i, r in enumerate(results))}

Combine these into a clear, concise response for the user."""

    result = subprocess.run(
        ["claude", "-p", combine_prompt, "--output-format", "json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout).get("result", "\n\n".join(results))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("Multi-Agent Release Orchestrator")
    print("Type 'exit' to quit\n")
    history = []

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye.")
            break
        if not user_input:
            continue

        response = manager_agent(user_input, history)

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})

        print(f"\nAssistant: {response}\n")

if __name__ == "__main__":
    main()
