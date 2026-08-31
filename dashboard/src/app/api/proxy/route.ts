import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const endpoint = searchParams.get('endpoint') || 'status';
  const limit = searchParams.get('limit');

  const apiUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';
  const apiKey = process.env.API_KEY || process.env.NEXT_PUBLIC_API_KEY || 'scratch_api_demo_key_982347';

  try {
    let targetUrl = `${apiUrl.replace(/\/$/, '')}/${endpoint}?api_key=${encodeURIComponent(apiKey)}`;
    if (limit) {
      targetUrl += `&limit=${encodeURIComponent(limit)}`;
    }

    const res = await fetch(targetUrl, {
      cache: 'no-store',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (!res.ok) {
      const errorText = await res.text();
      return NextResponse.json(
        { error: `Backend API error (${res.status}): ${errorText}` },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: `Could not connect to VPS API at ${apiUrl}: ${err.message}` },
      { status: 502 }
    );
  }
}
