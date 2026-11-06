/**
 * app/lib/session.ts
 * Readable session hints set by POST /api/login (aspira_role, aspira_lab_id, aspira_name).
 * UI only: the API re-checks every request against the signed, httpOnly session cookie.
 */

export type Role = 'admin' | 'lab' | 'logistics' | 'doctor';

export interface SessionHint {
  role: Role | null;
  labId: number | null;
  name: string;
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const hit = document.cookie.split('; ').find(c => c.startsWith(`${name}=`));
  if (!hit) return null;
  const raw = hit.slice(name.length + 1).replace(/^"|"$/g, '');
  try { return decodeURIComponent(raw); } catch { return raw; }
}

export function getSessionHint(): SessionHint {
  const role = readCookie('aspira_role')?.toLowerCase() as Role | undefined;
  const lab = Number(readCookie('aspira_lab_id'));
  return {
    role: role && ['admin', 'lab', 'logistics', 'doctor'].includes(role) ? role : null,
    labId: Number.isFinite(lab) && lab > 0 ? lab : null,
    name: readCookie('aspira_name') || '',
  };
}

export const ROLE_TITLES: Record<Role, string> = {
  admin: 'Administrator',
  lab: 'Lab Manager',
  logistics: 'Logistics',
  doctor: 'Doctor',
};
