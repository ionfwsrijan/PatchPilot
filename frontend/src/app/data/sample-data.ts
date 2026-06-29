import { Severity } from "../components/severity-chip";
import { Tool } from "../components/tool-badge";
import { Status } from "../components/status-pill";

export interface Finding {
  id: string;
  severity: Severity;
  category: string;
  title: string;
  file: string;
  lineNumber: number;
  tool: Tool;
  confidence: number;
  status: "open" | "accepted" | "ignored";
  description: string;
  code: string;
  suggestedFix?: string;
  references?: string[];
  ml_score?: number;
}

export interface Job {
  id: string;
  repoName: string;
  status: Status;
  timestamp: string;
  duration?: string;
  findingsCount: number;
}

export interface ScanTool {
  name: Tool;
  status: Status;
  startTime?: string;
  endTime?: string;
  findingsCount?: number;
}

export const sampleFindings: Finding[] = [
  {
    id: "F-001",
    severity: "critical",
    category: "SQL Injection",
    title: "Unsanitized user input in SQL query",
    file: "src/api/users.ts",
    lineNumber: 45,
    tool: "semgrep",
    confidence: 95,
    status: "open",
    description: "User-controlled input is directly interpolated into a SQL query without proper sanitization or parameterization.",
    code: `async function getUser(userId: string) {
  const query = \`SELECT * FROM users WHERE id = '\${userId}'\`;
  return await db.query(query);
}`,
    suggestedFix: `async function getUser(userId: string) {
  const query = 'SELECT * FROM users WHERE id = $1';
  return await db.query(query, [userId]);
}`,
    references: [
      "CWE-89: SQL Injection",
      "OWASP Top 10: A03:2021 – Injection",
    ],
    ml_score: 0.92,
  },
  {
    id: "F-002",
    severity: "high",
    category: "Vulnerable Dependency",
    title: "GHSA-cfm4-qjh2-z8j6: Express vulnerable to XSS",
    file: "package.json",
    lineNumber: 12,
    tool: "osv",
    confidence: 100,
    status: "open",
    description: "Express version 4.17.1 contains a known XSS vulnerability. Update to 4.19.2 or later.",
    code: `{
  "dependencies": {
    "express": "^4.17.1"
  }
}`,
    suggestedFix: `{
  "dependencies": {
    "express": "^4.19.2"
  }
}`,
    references: [
      "GHSA-cfm4-qjh2-z8j6",
      "CVE-2024-29041",
    ],
  },
  {
    id: "F-003",
    severity: "critical",
    category: "Hardcoded Secret",
    title: "AWS Access Key detected in source code",
    file: "config/aws.ts",
    lineNumber: 8,
    tool: "gitleaks",
    confidence: 100,
    status: "open",
    description: "A hardcoded AWS access key was detected. This poses a severe security risk.",
    code: `export const awsConfig = {
  region: 'us-east-1',
  accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
  secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
};`,
    suggestedFix: `import { SSMClient, GetParameterCommand } from '@aws-sdk/client-ssm';

export async function getAwsConfig() {
  const client = new SSMClient({ region: 'us-east-1' });
  const accessKey = await client.send(
    new GetParameterCommand({ Name: '/app/aws/access-key', WithDecryption: true })
  );
  return {
    region: 'us-east-1',
    accessKeyId: accessKey.Parameter?.Value,
  };
}`,
    references: [
      "AWS Security Best Practices",
      "CWE-798: Use of Hard-coded Credentials",
    ],
    ml_score: 0.96,
  },
  {
    id: "F-004",
    severity: "high",
    category: "Path Traversal",
    title: "Unsanitized file path from user input",
    file: "src/api/files.ts",
    lineNumber: 23,
    tool: "semgrep",
    confidence: 90,
    status: "open",
    description: "User input is used to construct file paths without validation, potentially allowing path traversal attacks.",
    code: `app.get('/download', (req, res) => {
  const filename = req.query.file;
  res.sendFile(\`./uploads/\${filename}\`);
});`,
    suggestedFix: `import path from 'path';

app.get('/download', (req, res) => {
  const filename = path.basename(req.query.file);
  const safePath = path.join(__dirname, 'uploads', filename);
  res.sendFile(safePath);
});`,
    references: [
      "CWE-22: Path Traversal",
      "OWASP: Path Traversal",
    ],
    ml_score: 0.78,
  },
  {
    id: "F-005",
    severity: "medium",
    category: "Vulnerable Dependency",
    title: "GHSA-7fh5-64p2-3v2j: lodash vulnerable to prototype pollution",
    file: "package.json",
    lineNumber: 15,
    tool: "osv",
    confidence: 100,
    status: "accepted",
    description: "Lodash version 4.17.19 has a prototype pollution vulnerability. Upgrade to 4.17.21.",
    code: `{
  "dependencies": {
    "lodash": "^4.17.19"
  }
}`,
    references: [
      "GHSA-7fh5-64p2-3v2j",
      "CVE-2020-8203",
    ],
    ml_score: 0.65,
  },
  {
    id: "F-006",
    severity: "medium",
    category: "Cross-Site Scripting",
    title: "Unescaped user input rendered in HTML",
    file: "src/components/UserProfile.tsx",
    lineNumber: 67,
    tool: "semgrep",
    confidence: 85,
    status: "open",
    description: "User-provided data is rendered without escaping, creating XSS vulnerability.",
    code: `function UserProfile({ user }) {
  return <div dangerouslySetInnerHTML={{ __html: user.bio }} />;
}`,
    suggestedFix: `import DOMPurify from 'dompurify';

function UserProfile({ user }) {
  const sanitizedBio = DOMPurify.sanitize(user.bio);
  return <div dangerouslySetInnerHTML={{ __html: sanitizedBio }} />;
}`,
    references: [
      "CWE-79: Cross-site Scripting (XSS)",
      "React Security Best Practices",
    ],
    ml_score: 0.58,
  },
  {
    id: "F-007",
    severity: "low",
    category: "Insecure Random",
    title: "Use of Math.random() for security-sensitive operation",
    file: "src/auth/token.ts",
    lineNumber: 34,
    tool: "semgrep",
    confidence: 80,
    status: "open",
    description: "Math.random() is not cryptographically secure and should not be used for security tokens.",
    code: `function generateToken() {
  return Math.random().toString(36).substring(2);
}`,
    suggestedFix: `import crypto from 'crypto';

function generateToken() {
  return crypto.randomBytes(32).toString('hex');
}`,
    references: [
      "CWE-330: Use of Insufficiently Random Values",
    ],
    ml_score: 0.35,
  },
  {
    id: "F-008",
    severity: "low",
    category: "Information Disclosure",
    title: "Detailed error messages exposed to client",
    file: "src/middleware/error.ts",
    lineNumber: 12,
    tool: "semgrep",
    confidence: 75,
    status: "ignored",
    description: "Stack traces and detailed error information should not be sent to clients in production.",
    code: `app.use((err, req, res, next) => {
  res.status(500).json({ error: err.message, stack: err.stack });
});`,
    references: [
      "CWE-209: Information Exposure Through an Error Message",
    ],
    ml_score: 0.22,
  },
  {
    id: "F-009",
    severity: "info",
    category: "Code Quality",
    title: "Deprecated API usage",
    file: "src/utils/crypto.ts",
    lineNumber: 56,
    tool: "semgrep",
    confidence: 90,
    status: "open",
    description: "The crypto.createCipher method is deprecated. Use crypto.createCipheriv instead.",
    code: `const cipher = crypto.createCipher('aes192', password);`,
    suggestedFix: `const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);`,
    references: [
      "Node.js Crypto Documentation",
    ],
    ml_score: 0.12,
  },
];

export const sampleJobs: Job[] = [
  {
    id: "JOB-2024-03-15-001",
    repoName: "acme-corp/payment-api",
    status: "completed",
    timestamp: "2024-03-15T14:23:00Z",
    duration: "2m 34s",
    findingsCount: 9,
  },
  {
    id: "JOB-2024-03-15-002",
    repoName: "acme-corp/web-frontend",
    status: "completed",
    timestamp: "2024-03-15T12:15:00Z",
    duration: "1m 52s",
    findingsCount: 3,
  },
  {
    id: "JOB-2024-03-14-003",
    repoName: "acme-corp/user-service",
    status: "completed",
    timestamp: "2024-03-14T18:45:00Z",
    duration: "3m 12s",
    findingsCount: 7,
  },
  {
    id: "JOB-2024-03-14-004",
    repoName: "acme-corp/notification-worker",
    status: "failed",
    timestamp: "2024-03-14T16:30:00Z",
    duration: "45s",
    findingsCount: 0,
  },
  {
    id: "JOB-2024-03-14-005",
    repoName: "acme-corp/analytics-pipeline",
    status: "completed",
    timestamp: "2024-03-14T10:22:00Z",
    duration: "4m 08s",
    findingsCount: 12,
  },
];

export const scanTools: ScanTool[] = [
  {
    name: "semgrep",
    status: "running",
    startTime: "14:23:05",
    findingsCount: 5,
  },
  {
    name: "osv",
    status: "completed",
    startTime: "14:23:05",
    endTime: "14:24:12",
    findingsCount: 2,
  },
  {
    name: "gitleaks",
    status: "pending",
  },
];
