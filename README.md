# Multi-Agent AI Orchestrator

A Python-based multi-agent orchestration system built with the Anthropic SDK and Claude Code.

## Overview
A manager agent that decomposes natural language requests and delegates tasks to specialist sub-agents for autonomous execution.

## Agents
- **Manager Agent** — interprets user requests and routes tasks
- **EC2 State Checker** — checks AWS EC2 instance status via AWS CLI
- **MR Prep Generator** — generates maintenance release deployment prep reports
- **General Assistant** — handles open-ended queries

## Features
- Natural language task decomposition
- Inter-agent communication
- Autonomous execution with tool use
- Modular specialist agent design

## Tech Stack
- Python
- Anthropic SDK (Claude API)
- AWS CLI / Boto3
- Claude Code

## Usage
```bash
pip install -r requirements.txt
python main.py
