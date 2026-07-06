import { NextRequest, NextResponse } from "next/server";
import { SourceType } from "@prisma/client";
import { z } from "zod";
import { prisma } from "@/lib/db";
import { isAdminRequest, unauthorized } from "@/lib/admin-auth";

const createSchema = z.object({
  name: z.string().min(1),
  type: z.nativeEnum(SourceType),
  enabled: z.boolean().default(true),
  priority: z.number().int().min(1).default(100),
  baseUrl: z.string().url().optional().or(z.literal("")),
  query: z.string().optional(),
  categoryKeys: z.array(z.string()).default([]),
});

export async function GET(request: NextRequest) {
  if (!(await isAdminRequest(request))) return unauthorized();
  const sources = await prisma.dataSource.findMany({ orderBy: { priority: "asc" } });
  return NextResponse.json({ sources });
}

export async function POST(request: NextRequest) {
  if (!(await isAdminRequest(request))) return unauthorized();
  const parsed = createSchema.parse(await request.json());
  const source = await prisma.dataSource.create({
    data: {
      ...parsed,
      baseUrl: parsed.baseUrl || null,
    },
  });
  return NextResponse.json({ source }, { status: 201 });
}

