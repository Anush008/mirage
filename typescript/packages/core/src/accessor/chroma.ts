// ========= Copyright 2026 @ Strukto.AI All Rights Reserved. =========
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
// ========= Copyright 2026 @ Strukto.AI All Rights Reserved. =========

import type { ChromaClient, Collection } from 'chromadb'
import { Accessor } from './base.ts'
import type { ChromaConfigResolved } from '../resource/chroma/config.ts'

export class ChromaAccessor extends Accessor {
  readonly config: ChromaConfigResolved
  private client: ChromaClient | null = null
  private collection: Collection | null = null

  constructor(config: ChromaConfigResolved) {
    super()
    this.config = config
  }

  async getClient(): Promise<ChromaClient> {
    if (this.client === null) {
      // chromadb is an optional peer dependency, loaded only when a
      // chroma mount is actually used
      const { ChromaClient } = await import('chromadb')
      this.client = new ChromaClient({
        host: this.config.host,
        port: this.config.port,
        ssl: this.config.ssl,
      })
    }
    return this.client
  }

  async getCollection(): Promise<Collection> {
    if (this.collection === null) {
      const client = await this.getClient()
      this.collection = await client.getCollection({
        name: this.config.collectionName,
      })
    }
    return this.collection
  }
}
