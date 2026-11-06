import { redirect } from 'next/navigation';

// Sample records live at /dashboard/reports/<sampleId>; the list of samples is Test Tracking.
export default function ReportsIndexPage() {
  redirect('/dashboard/tests');
}
