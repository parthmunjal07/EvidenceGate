export class ReplayRunGeneration {
  private value = 0;

  begin() {
    this.value += 1;
    return this.value;
  }

  current() {
    return this.value;
  }

  isCurrent(generation: number) {
    return generation === this.value;
  }
}
