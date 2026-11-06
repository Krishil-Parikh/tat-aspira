import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Pages each role may open. '/dashboard' matches only the home page; every other entry
// also covers its sub-pages (e.g. '/dashboard/reports' covers '/dashboard/reports/12').
// Keep in step with the sidebar (components/dashboard/Sidebar.tsx). The API enforces
// roles again on every request; this only keeps people on pages they can use.
const ROLE_ROUTES: Record<string, string[]> = {
  admin: ['*'],
  lab: [
    '/dashboard',
    '/dashboard/tests',
    '/dashboard/lab-queue',
    '/dashboard/lab-edos',
    '/dashboard/labs',
    '/dashboard/reports',
    '/tests',
  ],
  logistics: [
    '/dashboard',
    '/dashboard/logistics',
  ],
  doctor: [
    '/dashboard',
    '/dashboard/tests',
    '/dashboard/my-samples',
    '/dashboard/accession',
    '/dashboard/reports',
    '/tests',
  ],
};

// Where each role lands after login (and when it opens a page it may not use).
const ROLE_HOME: Record<string, string> = {
  admin: '/dashboard',
  lab: '/dashboard',
  logistics: '/dashboard/logistics',
  doctor: '/dashboard/my-samples',
};

function isAllowed(role: string, pathname: string): boolean {
  const routes = ROLE_ROUTES[role];
  if (!routes) return false;
  if (routes.includes('*')) return true;
  return routes.some(route =>
    route === '/dashboard'
      ? pathname === '/dashboard'
      : pathname === route || pathname.startsWith(route + '/')
  );
}

export function middleware(request: NextRequest) {
  const authCookie = request.cookies.get('aspira_auth');
  const roleCookie = request.cookies.get('aspira_role');
  const { pathname } = request.nextUrl;

  // 1. Protect dashboard and test detail routes
  if (pathname.startsWith('/dashboard') || pathname.startsWith('/tests')) {
    if (!authCookie) {
      const response = NextResponse.redirect(new URL('/login', request.url));
      // Set secure cookie flags for the redirect response
      response.cookies.set('aspira_redirect', pathname, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'strict',
        maxAge: 300 // 5 minutes
      });
      return response;
    }

    // 2. RBAC — unknown or missing role means the session is not usable: log in again
    const role = roleCookie?.value?.toLowerCase() ?? '';
    if (!ROLE_ROUTES[role]) {
      return NextResponse.redirect(new URL('/login', request.url));
    }
    const home = ROLE_HOME[role];
    if (pathname === '/dashboard' && home !== '/dashboard') {
      return NextResponse.redirect(new URL(home, request.url));
    }
    if (!isAllowed(role, pathname)) {
      return NextResponse.redirect(new URL(home, request.url));
    }
  }

  // 3. Already logged in → skip login page
  const loginRole = roleCookie?.value?.toLowerCase() ?? '';
  if (pathname === '/login' && authCookie && ROLE_HOME[loginRole]) {
    return NextResponse.redirect(new URL(ROLE_HOME[loginRole], request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/tests/:path*', '/login'],
};
