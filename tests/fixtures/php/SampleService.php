<?php

declare(strict_types=1);

namespace Acme\Tests\Fixtures;

/**
 * Sample service used by autotest's own test suite to exercise the
 * tree-sitter PHP walker. Do NOT use this as a coding-style reference;
 * it intentionally mixes shapes so the AST walker has variety to
 * stumble over.
 */
final class SampleService
{
    private int $counter = 0;

    /**
     * Add the two integers and return the sum.
     */
    public function add(int $a, int $b): int
    {
        return $a + $b;
    }

    public function increment(): int
    {
        return ++$this->counter;
    }

    protected function shouldNotAppear(): bool
    {
        return false;
    }

    private function alsoHidden(): void
    {
        // private methods must not appear in inventory output
    }
}

/**
 * Top-level function, no class wrapper.
 */
function bare_function(string $name): string
{
    return strtoupper($name);
}
