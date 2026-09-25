/** The root sends people to their projects; signed-out visitors are sent on to sign in. */
import { redirect } from "next/navigation"

export default function Home() {
  redirect("/projects")
}
