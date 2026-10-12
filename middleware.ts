import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Full RBAC route map per PRD role spec
const ROLE_ROUTES: Record<string, string[]> = {
  admin: [
    '/dashboard',
    '/dashboard/labs',
    '/dashboard/catalog',
    '/dashboard/accession',
    '/dashboard/admin',
    '/dashboard/reports',
    '/dashboard/my-samples',
    '/tests',
  ],
  lab: [
    '/dashboard',
    '/dashboard/labs',
    '/dashboard/lab-queue',
    '/dashboard/reports',
    '/dashboard/lab-edos',
    '/tests',
  ],
  logistics: [
    '/dashboard',
    '/dashboard/logistics',
  ],
  doctor: [
    '/dashboard',
    '/dashboard/accession',
    '/dashboard/my-samples',
    '/dashboard/reports',
    '/tests',
  ],
};

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

    // 2. RBAC — check allowed routes for this role
    const role = roleCookie?.value?.toLowerCase() || 'admin';
    const allowedRoutes = ROLE_ROUTES[role] || ROLE_ROUTES.admin;

    const isAllowed = allowedRoutes.some(
      route => pathname === route || pathname.startsWith(route + '/')
    );

    if (!isAllowed) {
      // Redirect unauthorized access to their home
      return NextResponse.redirect(new URL('/dashboard', request.url));
    }
  }

  // 3. Already logged in → skip login page
  if (pathname === '/login' && authCookie) {
    return NextResponse.redirect(new URL('/dashboard', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/tests/:path*', '/login'],
};
